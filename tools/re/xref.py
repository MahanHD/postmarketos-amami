"""Find Thumb BL/BLX call sites of the given functions in a stock ARM library.

  xref.py lib.so symbol...
"""
import sys
import capstone
from elftools.elf.elffile import ELFFile

path = sys.argv[1]
e = ELFFile(open(path, "rb"))
data = open(path, "rb").read()
text = e.get_section_by_name(".text")
base, off, size = text['sh_addr'], text['sh_offset'], text['sh_size']
funcs = []
targets = {}
for s in e.get_section_by_name(".dynsym").iter_symbols():
    if s['st_info']['type'] == 'STT_FUNC' and s['st_value']:
        funcs.append((s['st_value'] & ~1, s.name))
        if s.name in sys.argv[2:]:
            targets[s['st_value'] & ~1] = s.name
funcs.sort()
import bisect
starts = [f[0] for f in funcs]
code = data[off:off + size]
for i in range(0, size - 4, 2):
    hw1 = int.from_bytes(code[i:i + 2], "little")
    hw2 = int.from_bytes(code[i + 2:i + 4], "little")
    if (hw1 & 0xf800) != 0xf000 or (hw2 & 0xc000) != 0xc000:
        continue
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3ff
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    imm11 = hw2 & 0x7ff
    i1 = 1 - (j1 ^ s)
    i2 = 1 - (j2 ^ s)
    imm = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if s:
        imm -= 1 << 25
    pc = base + i + 4
    t = pc + imm
    if not (hw2 & 0x1000):  # BLX to ARM
        t &= ~3
    if t in targets:
        k = bisect.bisect_right(starts, base + i) - 1
        print("%08x in %s -> %s" % (base + i, funcs[k][1], targets[t]))
