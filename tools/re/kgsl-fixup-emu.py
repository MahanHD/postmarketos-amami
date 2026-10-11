"""Run the stock kernel's adreno_a3xx_pwron_fixup_init() and dump the buffer it builds.

The stock 14.6.A.1.236 kernel has no symbols; the function was found through the
literal-pool reference to its shader (_a3xx_pwron_fixup_fs_instructions). It is run
in ARM mode under Unicorn with the image mapped at 0xc0008000. Its four calls
(kgsl_allocate_contiguous, a helper, memcpy, set_bit) are stubbed; the adreno_device
offsets used (priv +0x5c0, pwron_fixup.hostptr +0x6f4, pwron_fixup_dwords +0x724)
come from its disassembly.

  kgsl-fixup-emu.py vmlinux-stock.bin out.bin
"""
import struct
import sys
import unicorn as uc
from unicorn.arm_const import *

BASE = 0xc0008000
FUNC = 0xc04832f8
ALLOC, HELPER, MEMCPY, SET_BIT = 0xc04640f8, 0xc04685c0, 0xc0392480, 0xc0392d10
DEV, BUF, STK, RET = 0x10000000, 0x20000000, 0x30000000, 0x40000000

img = open(sys.argv[1], "rb").read()
mu = uc.Uc(uc.UC_ARCH_ARM, uc.UC_MODE_ARM)
mu.mem_map(BASE, ((len(img) + 0xfff) & ~0xfff) + 0x100000)
mu.mem_write(BASE, img)
for a in (DEV, BUF, STK - 0x10000, RET):
    mu.mem_map(a, 0x10000)
mu.mem_write(DEV + 0x6f4, struct.pack("<I", BUF))


def hook(mu, addr, size, user):
    if addr == RET:
        mu.emu_stop()
        return
    if addr in (ALLOC, HELPER, MEMCPY, SET_BIT):
        r0, r1, r2 = (mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        if addr == MEMCPY:
            mu.mem_write(r0, bytes(mu.mem_read(r1, r2)))
        mu.reg_write(UC_ARM_REG_R0, r0 if addr == MEMCPY else 0)
        mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR))


mu.hook_add(uc.UC_HOOK_CODE, hook)
mu.reg_write(UC_ARM_REG_R0, DEV)
mu.reg_write(UC_ARM_REG_SP, STK - 0x100)
mu.reg_write(UC_ARM_REG_LR, RET)
mu.emu_start(FUNC, RET)
n = struct.unpack("<I", mu.mem_read(DEV + 0x724, 4))[0]
open(sys.argv[2], "wb").write(bytes(mu.mem_read(BUF, 4 * n)))
print(n, "dwords")
