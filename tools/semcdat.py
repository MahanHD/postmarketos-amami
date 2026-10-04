#!/usr/bin/env python3
"""Dump the register tables in a Sony camera module file
(/system/vendor/camera/<MODULE>_<SENSOR>.dat on stock 14.6.A.1.236).

Entries are 12 bytes: u32 address, u32 value, u32 0xffff0000. Runs of them
are tables: an init table, one table per sensor mode, stream on/off, test
pattern and so on. The header before them holds per-mode geometry.
Usage: semcdat.py SOI20BS0_IMX200.dat
"""
import struct, sys
d = open(sys.argv[1], "rb").read()
runs = []; i = 0
while i + 12 <= len(d):
    a, v, t = struct.unpack_from("<III", d, i)
    if a < 0x10000 and v < 0x10000 and t == 0xffff0000:
        j = i; regs = []
        while j + 12 <= len(d):
            a, v, t = struct.unpack_from("<III", d, j)
            if not (a < 0x10000 and v < 0x10000 and t == 0xffff0000): break
            regs.append((a, v)); j += 12
        runs.append((i, regs)); i = j
    else:
        i += 4
for off, regs in runs:
    print("== table at %d (%#x), %d regs" % (off, off, len(regs)))
    print("   " + " ".join("%04x=%02x" % (a, v) for a, v in regs))
