#!/usr/bin/env python3
"""Set the CSIPHY0 HS settle count once camss has powered the PHY.

Waits for camss_csi0phy_clk to be enabled first: touching CSIPHY registers
through /dev/mem with the clock off can hang the bus. Usage: setsettle.py N
"""
import mmap, os, struct, sys, time
val = int(sys.argv[1])
def phy_on():
    for l in open("/sys/kernel/debug/clk/clk_summary"):
        f = l.split()
        if f and f[0] == "camss_csi0phy_clk": return int(f[1]) > 0
    return False
t = time.time()
while not phy_on():
    if time.time() - t > 20: print("setsettle: phy clock never came on"); sys.exit(1)
    time.sleep(0.005)
time.sleep(0.05)                       # let camss finish lanes_enable
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0xfda0a000)
before = struct.unpack_from("<I", m, 0xc08)[0]
for l in (0, 1, 2, 3, 4): struct.pack_into("<I", m, 0xc08 + 0x40*l, val)
print("setsettle: %d -> %d after %.3f s" % (before, val, time.time() - t))
