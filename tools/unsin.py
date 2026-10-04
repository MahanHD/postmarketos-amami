#!/usr/bin/env python3
"""Unpack a Sony SIN v3 image (from an FTF) into a raw partition image.

The payload is an MMCF map: ADDR records give each chunk's source offset,
length and destination offset. Chunks are written at their destination, so
the output is a sparse raw image (system.sin -> ext4, read it with debugfs).
Usage: unsin.py system.sin system.img
"""
import struct, sys
fn, out = sys.argv[1], sys.argv[2]
f = open(fn, "rb")
h = f.read(8); hlen = struct.unpack(">I", h[4:8])[0]
f.seek(hlen); assert f.read(4) == b"MMCF"
mlen = struct.unpack(">I", f.read(4))[0]
mm = f.read(mlen); base = hlen + 8 + mlen
recs = []; i = 0
while i < len(mm):
    tag = mm[i:i+4]; ln = struct.unpack(">I", mm[i+4:i+8])[0]
    if tag == b"ADDR":
        src, dl, dst = struct.unpack(">QQQ", mm[i+8:i+32])
        recs.append((src, dl, dst))
    i += ln
print("%d ADDR records, data base %#x" % (len(recs), base))
f.seek(base + recs[0][0]); print("first chunk starts", f.read(16))
o = open(out, "wb"); end = 0
for src, dl, dst in recs:
    f.seek(base + src); o.seek(dst)
    left = dl
    while left:
        b = f.read(min(left, 1 << 24)); o.write(b); left -= len(b)
    end = max(end, dst + dl)
o.truncate(end); print("image size", end)
