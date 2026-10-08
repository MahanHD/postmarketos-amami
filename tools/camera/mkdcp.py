#!/usr/bin/env python3
"""Write a DNG camera profile (DCP) for the rear IMX200, for Megapixels.

  mkdcp.py out.dcp

The colour comes from the stock firmware: SOI20BS0/color_ctrl.dat holds one
colour matrix, int16 in Q10, which stock applies to white-balanced camera RGB
to get linear sRGB at every colour temperature. A DCP wants two matrices:

  ForwardMatrix1  white-balanced camera RGB -> XYZ (D50)
                  = Bradford(D65->D50) . sRGB->XYZ . stock
  ColorMatrix1    XYZ (D65) -> raw camera RGB
                  = diag(daylight neutral) . stock^-1 . XYZ->sRGB

The daylight neutral is the raw response to a white surface in daylight,
measured on this camera: R/G 0.485, B/G 0.62 (black level removed).
"""
import struct
import sys

import numpy as np

STOCK_Q10 = [1387, -462, 99, -182, 1329, -123, 35, -383, 1372]
DAYLIGHT_NEUTRAL = (0.485, 1.0, 0.62)

SRGB_TO_XYZ_D65 = np.array([[0.4124564, 0.3575761, 0.1804375],
                            [0.2126729, 0.7151522, 0.0721750],
                            [0.0193339, 0.1191920, 0.9503041]])
BRADFORD_D65_TO_D50 = np.array([[1.0478112, 0.0228866, -0.0501270],
                                [0.0295424, 0.9904844, -0.0170491],
                                [-0.0092345, 0.0150436, 0.7521316]])

# TIFF/DNG tags
UNIQUE_CAMERA_MODEL = 50708
COLOR_MATRIX_1 = 50721
CALIBRATION_ILLUMINANT_1 = 50778
PROFILE_NAME = 50936
PROFILE_EMBED_POLICY = 50941
FORWARD_MATRIX_1 = 50964
ILLUMINANT_D65 = 21

ASCII, SHORT, LONG, SRATIONAL = 2, 3, 4, 10


def matrices():
    stock = np.array(STOCK_Q10, dtype=float).reshape(3, 3) / 1024
    forward = BRADFORD_D65_TO_D50 @ SRGB_TO_XYZ_D65 @ stock
    color = np.diag(DAYLIGHT_NEUTRAL) @ np.linalg.inv(stock) @ np.linalg.inv(SRGB_TO_XYZ_D65)
    return color, forward


def write_dcp(path, color, forward):
    entries = []

    def srational(m):
        vals = []
        for v in m.flatten():
            vals += [int(round(v * 10000)), 10000]
        return struct.pack("<%di" % len(vals), *vals), len(m.flatten())

    def ascii(s):
        b = s.encode() + b"\0"
        return b, len(b)

    data, n = ascii("Sony Xperia Z1 Compact IMX200")
    entries.append((UNIQUE_CAMERA_MODEL, ASCII, n, data))
    data, n = srational(color)
    entries.append((COLOR_MATRIX_1, SRATIONAL, n, data))
    entries.append((CALIBRATION_ILLUMINANT_1, SHORT, 1, struct.pack("<H", ILLUMINANT_D65)))
    data, n = ascii("Stock SOI20BS0")
    entries.append((PROFILE_NAME, ASCII, n, data))
    entries.append((PROFILE_EMBED_POLICY, LONG, 1, struct.pack("<I", 3)))
    data, n = srational(forward)
    entries.append((FORWARD_MATRIX_1, SRATIONAL, n, data))
    entries.sort()

    # "IIRC" header, then one IFD, then the values that do not fit in 4 bytes
    ifd_size = 2 + 12 * len(entries) + 4
    data_off = 8 + ifd_size
    ifd = struct.pack("<H", len(entries))
    blob = b""
    for tag, typ, count, data in entries:
        if len(data) <= 4:
            ifd += struct.pack("<HHI", tag, typ, count) + data.ljust(4, b"\0")
        else:
            ifd += struct.pack("<HHII", tag, typ, count, data_off + len(blob))
            blob += data
            if len(blob) % 2:
                blob += b"\0"
    ifd += struct.pack("<I", 0)
    with open(path, "wb") as f:
        f.write(b"IIRC" + struct.pack("<I", 8) + ifd + blob)


def main():
    color, forward = matrices()
    np.set_printoptions(precision=4, suppress=True)
    print("ColorMatrix1 (XYZ D65 -> camera)\n", color)
    print("ForwardMatrix1 (camera -> XYZ D50)\n", forward)
    write_dcp(sys.argv[1], color, forward)


if __name__ == "__main__":
    main()
