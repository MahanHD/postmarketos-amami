"""Disassemble one function of a stock ARM shared library, with symbol names.

  armdis.py lib.so symbol_or_hexaddr [max_bytes]

Calls into the PLT are named after their relocation; literal-pool loads show the
loaded word.
"""
import struct, sys
import capstone
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection

path, what = sys.argv[1], sys.argv[2]
n = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
data = open(path, "rb").read()
e = ELFFile(open(path, "rb"))
dynsym = e.get_section_by_name(".dynsym")
syms = {}
byname = {}
sizes = {}
for s in dynsym.iter_symbols():
    if s['st_value'] and s['st_info']['type'] == 'STT_FUNC':
        syms[s['st_value'] & ~1] = s.name
        byname[s.name] = s['st_value']
        sizes[s.name] = s['st_size']

def v2o(v):
    for s in e.iter_segments():
        if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= v < s['p_vaddr'] + s['p_filesz']:
            return v - s['p_vaddr'] + s['p_offset']

# PLT: map stub address -> import name via .rel.plt order
plt = e.get_section_by_name(".plt")
relplt = e.get_section_by_name(".rel.plt")
if plt and relplt:
    names = [dynsym.get_symbol(r['r_info_sym']).name for r in relplt.iter_relocations()]
    base = plt['sh_addr'] + 20
    for i, nm in enumerate(names):
        syms[base + 12 * i] = nm + "@plt"

if what in byname:
    addr = byname[what]
    n = n or sizes[what]
else:
    addr = int(what, 16)
    n = n or 512
thumb = addr & 1
a = addr & ~1
o = v2o(a)
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB if thumb else capstone.CS_MODE_ARM)
md.detail = True
for i in md.disasm(data[o:o + n], a):
    note = ""
    if i.mnemonic.startswith(("bl", "b")) and i.op_str.startswith("#"):
        t = int(i.op_str[1:], 16)
        if t in syms:
            note = "<%s>" % syms[t]
    if i.mnemonic.startswith("ldr") and "[pc" in i.op_str:
        try:
            disp = i.operands[1].mem.disp
            la = ((i.address + (4 if thumb else 8)) & ~3) + disp
            note = "=0x%08x" % struct.unpack_from("<I", data, v2o(la))[0]
        except Exception:
            pass
    print("%08x: %-8s %-32s %s" % (i.address, i.mnemonic, i.op_str, note))
