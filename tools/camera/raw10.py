#!/usr/bin/env python3
"""Look at RAW10 captures from capture.sh on the host.

  raw10.py capture.raw stats            per-frame level statistics
  raw10.py capture.raw png out.png      last frame as a quick preview PNG

The preview is deliberately crude: black level 64 subtracted, 2x2 Bayer
quads averaged (RGGB), grey-world white balance, gamma 2.2, and rotated 90
degrees clockwise because the module is mounted sideways. No lens shading.
"""
import struct, sys, zlib
import numpy as np

W, H = 5248, 3936
STRIDE = W * 10 // 8
BLACK = 64


def frames(path):
    raw = np.fromfile(path, dtype=np.uint8)
    n = raw.size // (STRIDE * H)
    return [raw[k * STRIDE * H:(k + 1) * STRIDE * H].reshape(H, STRIDE) for k in range(n)]


def unpack(fr):
    g = fr.reshape(H, W // 4, 5).astype(np.uint16)
    px = np.empty((H, W), np.uint16)
    for k in range(4):
        px[:, k::4] = (g[:, :, k] << 2) | ((g[:, :, 4] >> (2 * k)) & 3)
    return px


def write_png(path, img):
    h, w, _ = img.shape
    rows = b"".join(b"\0" + img[y].tobytes() for y in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def preview(px):
    p = px.astype(np.float32) - BLACK
    rgb = np.stack([p[0::2, 0::2], (p[0::2, 1::2] + p[1::2, 0::2]) / 2, p[1::2, 1::2]], -1)[::3, ::3]
    rgb = np.clip(rgb, 0, None)
    for c in range(3):
        rgb[..., c] *= rgb[..., 1].mean() / max(rgb[..., c].mean(), 1e-3)
    rgb = np.clip(rgb / max(np.percentile(rgb, 99.5), 1e-3), 0, 1) ** (1 / 2.2)
    return np.ascontiguousarray(np.rot90((rgb * 255).astype(np.uint8), -1))


def main():
    path, cmd = sys.argv[1], sys.argv[2]
    fr = frames(path)
    if not fr:
        sys.exit("no complete frame in %s" % path)
    if cmd == "stats":
        for k, f in enumerate(fr):
            px = unpack(f)
            q = np.percentile(px, [1, 50, 99]).astype(int)
            print("frame %d: mean %.1f  p1/p50/p99 %s" % (k, px.mean(), q))
    elif cmd == "png":
        write_png(sys.argv[3], preview(unpack(fr[-1])))


if __name__ == "__main__":
    main()
