#!/usr/bin/env python3
"""mmio.py ADDR [VALUE]: read (or write) one 32-bit register through /dev/mem.
mmio.py dump BASE LEN: print every 32-bit word in [BASE, BASE+LEN) as 'addr: value'."""
import mmap, os, struct, sys
fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
def window(addr, length):
    page = addr & ~0xfff
    size = (addr + length - page + 0xfff) & ~0xfff
    return mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=page), addr - page
if sys.argv[1] == 'dump':
    base, length = int(sys.argv[2], 0), int(sys.argv[3], 0)
    m, off = window(base, length)
    for i in range(0, length, 4):
        print('%08x: %08x' % (base + i, struct.unpack('<I', m[off + i:off + i + 4])[0]))
else:
    addr = int(sys.argv[1], 0)
    m, off = window(addr, 4)
    if len(sys.argv) > 2:
        m[off:off + 4] = struct.pack('<I', int(sys.argv[2], 0))
    print('%08x: %08x' % (addr, struct.unpack('<I', m[off:off + 4])[0]))
