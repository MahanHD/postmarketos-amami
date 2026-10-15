#!/usr/bin/env python3
"""Find the frames rowwatch recorded out of place.

    rowwatch.py out.bin height [reference_frame]

Each frame's row profile is compared with the reference frame's (default:
frame 10, past the oversized start-up frames) by circular cross-correlation.
Prints every change of shift with its frame number, sequence and time, plus
sequence gaps (frames the VFE dropped) and frames whose size is unexpected.
"""
import sys

import numpy as np

path, h = sys.argv[1], int(sys.argv[2])
ref_n = int(sys.argv[3]) if len(sys.argv) > 3 else 10
rec = np.dtype([("seq", "<u4"), ("used", "<u4"), ("ts", "<u8"), ("prof", "<u2", h)])
d = np.fromfile(path, rec)
print(f"{len(d)} frames, sequence {d['seq'][0]}..{d['seq'][-1]}")

ref = d["prof"][ref_n].astype(float)
ref -= ref.mean()
fr = np.fft.rfft(ref)
last = None
for i, r in enumerate(d):
    p = r["prof"].astype(float)
    p -= p.mean()
    cc = np.fft.irfft(np.fft.rfft(p) * np.conj(fr), n=h)
    s = int(cc.argmax())
    s = s if s < h // 2 else s - h
    if s != last:
        t = (r["ts"] - d["ts"][0]) / 1e6
        print(f"frame {i} seq {r['seq']} t {t:.2f}s: shift {s}")
        last = s
    if i and r["seq"] != d["seq"][i - 1] + 1:
        print(f"frame {i}: sequence {d['seq'][i - 1]} -> {r['seq']}")
used = set(d["used"].tolist())
if len(used) > 1:
    print("bytesused values:", sorted(used))
