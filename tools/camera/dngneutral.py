#!/usr/bin/env python3
"""Grey-world neutral of a full-size Megapixels DNG from the rear camera.

  dngneutral.py photo.dng [strip_offset]

Unpacks the raw strip (5248x3936, 10-bit MSB-first, RGGB, black level 64),
averages each channel over the pixels clipped in none of them, and prints
R/G and B/G: what AsShotNeutral should roughly be for a scene without one
dominant colour. Without strip_offset it asks exiftool for StripOffsets.
"""
import subprocess
import sys

import numpy as np

W, H, BLACK, CLIP = 5248, 3936, 64, 900

path = sys.argv[1]
if len(sys.argv) > 2:
    off = int(sys.argv[2])
else:
    out = subprocess.run(['exiftool', '-s3', '-StripOffsets', path],
                         capture_output=True, text=True, check=True).stdout
    off = int(out.split()[0])

d = np.fromfile(path, np.uint8, count=W * H * 10 // 8, offset=off)
b = d.reshape(-1, 5).astype(np.uint16)
v = np.empty((b.shape[0], 4), np.uint16)
v[:, 0] = (b[:, 0] << 2) | (b[:, 1] >> 6)
v[:, 1] = ((b[:, 1] & 63) << 4) | (b[:, 2] >> 4)
v[:, 2] = ((b[:, 2] & 15) << 6) | (b[:, 3] >> 2)
v[:, 3] = ((b[:, 3] & 3) << 8) | b[:, 4]
im = v.reshape(H, W).astype(float) - BLACK

r, g1, g2, bl = im[::2, ::2], im[::2, 1::2], im[1::2, ::2], im[1::2, 1::2]
ok = (r < CLIP) & (g1 < CLIP) & (g2 < CLIP) & (bl < CLIP)
R, G, B = r[ok].mean(), (g1[ok].mean() + g2[ok].mean()) / 2, bl[ok].mean()
print('R %.1f G %.1f B %.1f  R/G %.3f B/G %.3f  clipped %.2f%%'
      % (R, G, B, R / G, B / G, 100 - 100 * ok.mean()))
