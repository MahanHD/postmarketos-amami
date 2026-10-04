#!/usr/bin/env python3
"""Sweep the CSIPHY0 HS settle count during a running stream and report, per
value: PHY error interrupts, VFE interrupts, CSID packet/ECC counters and the
per-lane PHY status. Run while a capture is streaming (the PHY must be on).
Usage: settle-sweep.py 1,2,3,5,7,9,11
"""
import mmap, os, struct, time, sys
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0xfda0a000)
c = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0xfda08000)
P = 0xc00
def r(mm, o): return struct.unpack_from("<I", mm, o)[0]
def w(mm, o, v): struct.pack_into("<I", mm, o, v)
def irqs(name):
    for l in open("/proc/interrupts"):
        if l.rstrip().endswith(name): return sum(int(x) for x in l.split()[1:3])
    return 0
lanes = (0, 1, 2, 3, 4)
orig = r(m, P + 0x008)
print("orig settle %d" % orig)
vals = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else list(range(2, 64, 3))
for v in vals + [orig]:
    for l in lanes: w(m, P + 0x008 + 0x40*l, v)
    time.sleep(0.2)
    a = irqs("camss_msm_csiphy0"); v0 = irqs("camss_msm_vfe0"); p0 = r(c, 0x90); e0 = r(c, 0x94)
    acc = [0]*8; t = time.time()
    while time.time() - t < 1.0:
        for i in range(8): acc[i] |= r(m, P + 0x18c + 4*i)
    b = irqs("camss_msm_csiphy0"); v1 = irqs("camss_msm_vfe0"); p1 = r(c, 0x90); e1 = r(c, 0x94)
    print("settle %2d: phy irq/s %7d  vfe irq/s %5d  csid 090 %08x->%08x 094 %08x->%08x  status %s" % (v, b-a, v1-v0, p0, p1, e0, e1, " ".join("%02x" % x for x in acc[:7])))
    sys.stdout.flush()
