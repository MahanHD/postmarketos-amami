"""Run one function of a stock ARM shared library under Unicorn.

Used to see exactly which GPU commands the stock Adreno driver writes, without
having to decode compiler output by hand. The library is mapped at its link
address with R_ARM_RELATIVE relocations applied; imported functions return 0;
any memory touched outside the mapping reads as zeros.

  from armemu import Emu
  e = Emu("libGLESv2_adreno.so")
  e.write32(addr, value) ...
  e.call("symbol", r0, r1, ..., stack=[...])
"""
import struct
import unicorn as uc
from unicorn.arm_const import *
from elftools.elf.elffile import ELFFile

PAGE = 0x1000
RET_MAGIC = 0x0ff00000
STACK_TOP = 0x0fe00000


class Emu:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        self.elf = ELFFile(open(path, "rb"))
        self.mu = uc.Uc(uc.UC_ARCH_ARM, uc.UC_MODE_THUMB)
        self.mapped = set()
        for s in self.elf.iter_segments():
            if s['p_type'] != 'PT_LOAD':
                continue
            self.map(s['p_vaddr'], s['p_memsz'])
            self.mu.mem_write(s['p_vaddr'], s.data())
        self.syms = {}
        dynsym = self.elf.get_section_by_name(".dynsym")
        for s in dynsym.iter_symbols():
            if s['st_value']:
                self.syms[s.name] = s['st_value']
        # relocations
        self.imports = {}
        stub = 0x0fd00000
        self.map(stub, 0x10000)
        for name in (".rel.dyn", ".rel.plt"):
            sec = self.elf.get_section_by_name(name)
            if not sec:
                continue
            for r in sec.iter_relocations():
                t = r['r_info_type']
                off = r['r_offset']
                if t == 23:  # R_ARM_RELATIVE
                    v = struct.unpack("<I", self.mu.mem_read(off, 4))[0]
                    self.write32(off, v)
                elif t in (21, 22, 2):  # GLOB_DAT, JUMP_SLOT, ABS32
                    sym = dynsym.get_symbol(r['r_info_sym'])
                    if sym['st_value']:
                        self.write32(off, sym['st_value'])
                    else:
                        if sym.name not in self.imports:
                            self.imports[sym.name] = stub
                            # movs r0,#0 ; bx lr  (thumb)
                            self.mu.mem_write(stub, b"\x00\x20\x70\x47")
                            stub += 8
                        self.write32(off, self.imports[sym.name] | 1)
        self.stub_names = {v: k for k, v in self.imports.items()}
        self.map(STACK_TOP - 0x100000, 0x100000)
        self.map(RET_MAGIC, PAGE)
        self.mu.hook_add(uc.UC_HOOK_MEM_UNMAPPED, self._fault)
        self.mu.hook_add(uc.UC_HOOK_CODE, self._code, begin=0x0fd00000, end=0x0fd10000)
        self.calls = []

    def map(self, addr, size):
        a = addr & ~(PAGE - 1)
        end = (addr + size + PAGE - 1) & ~(PAGE - 1)
        for p in range(a, end, PAGE):
            if p not in self.mapped:
                self.mu.mem_map(p, PAGE)
                self.mapped.add(p)

    def _fault(self, mu, access, addr, size, value, _):
        self.map(addr, size)
        return True

    def _code(self, mu, addr, size, _):
        name = self.stub_names.get(addr & ~1)
        if name:
            self.calls.append((name, [mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]))

    def write32(self, addr, v):
        self.map(addr, 4)
        self.mu.mem_write(addr, struct.pack("<I", v & 0xffffffff))

    def read32(self, addr):
        return struct.unpack("<I", self.mu.mem_read(addr, 4))[0]

    def read(self, addr, n):
        return bytes(self.mu.mem_read(addr, n))

    def call(self, fn, *args, stack=()):
        addr = self.syms[fn] if isinstance(fn, str) else fn
        regs = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
        for r, v in zip(regs, args):
            self.mu.reg_write(r, v)
        sp = STACK_TOP - 0x1000
        for i, v in enumerate(stack):
            self.write32(sp + 4 * i, v)
        self.mu.reg_write(UC_ARM_REG_SP, sp)
        self.mu.reg_write(UC_ARM_REG_LR, RET_MAGIC | 1)
        self.mu.emu_start(addr | 1, RET_MAGIC, count=5_000_000)
        return self.mu.reg_read(UC_ARM_REG_R0)
