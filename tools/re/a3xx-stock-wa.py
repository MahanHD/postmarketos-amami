#!/usr/bin/env python3
"""Show the GPU commands the stock Adreno driver adds for a3xx hardware bugs.

  MESA_REGS=.../src/freedreno/registers/adreno a3xx-stock-wa.py libGLESv2_adreno.so [flags0 flags1]

Runs the stock workaround code (oxili_wa_*) from libGLESv2_adreno.so under
Unicorn and decodes what it writes. The flags default to the set
oxili_detect_workarounds() picks for this phone's GPU, chip id 3.3.0.1
(0xc2878307 and 0x1b). The scratch buffer address in the preamble shows up as
0x12340000 (RB_COPY_DEST_BASE holds it shifted, as 0x091a0000).
"""
import sys

from armemu import Emu
from pm4dec import decode

CTX, WA, BUF, PROG, BIN = 0x20000000, 0x21000000, 0x22000000, 0x23000000, 0x24000000
SCRATCH = 0x12340000


def main():
    lib = sys.argv[1]
    f0 = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0xc2878307
    f1 = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x1b
    e = Emu(lib)
    e.write32(CTX + 0x1868, WA)
    e.write32(WA, f0)
    e.write32(WA + 4, f1)
    e.write32(WA + 0x18, SCRATCH)
    # a program whose HLSQ_CONTROL_0 has every bit set, to show which ones
    # the post-draw rewrite clears
    e.write32(CTX + 0x1050, PROG)
    e.write32(PROG + 0x1b8, BIN)
    e.write32(BIN + 0x108 * 2 + 0x24, 0xffffffff)

    def show(title, start, end):
        dw = [e.read32(a) for a in range(start, end, 4)]
        print("%s (%d dwords)" % (title, len(dw)))
        decode(dw)
        print()

    show("context preamble", BUF, e.call("oxili_wa_preamble_init_cmds", CTX, BUF))
    for num in (0, 6):
        show("before a draw (arg %d)" % num, BUF,
             e.call("oxili_wa_predraw", CTX, BUF, 2, 0, stack=[0, WA, num]))
        show("after a draw (arg %d)" % num, BUF,
             e.call("oxili_wa_postdraw", CTX, BUF, 2, 0, stack=[0, WA, num]))


if __name__ == "__main__":
    main()
