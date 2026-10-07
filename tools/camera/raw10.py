#!/usr/bin/env python3
"""Look at RAW10 captures from capture.sh on the host.

  raw10.py capture.raw stats            per-frame level statistics
  raw10.py capture.raw png out.png [eeprom.bin]
                                        last frame as a quick preview PNG

The preview is deliberately crude: black level 64 subtracted, 2x2 Bayer
quads averaged (RGGB), grey-world white balance, gamma 2.2, and rotated 90
degrees clockwise because the module is mounted sideways.

Given a dump of the module EEPROM it also corrects lens shading. The module
stores its factory calibration at 0x100: 64-byte blocks, each a 9x7 grid of
relative brightness (0x80 = the centre) plus one trailing byte, taken here
as R, Gr, Gb, B in that order.
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


def shading_gain(grid, h, w):
    """Bilinear interpolation of 0x80 / grid across an h x w channel."""
    gy = np.linspace(0, grid.shape[0] - 1, h)
    gx = np.linspace(0, grid.shape[1] - 1, w)
    y0 = np.clip(gy.astype(int), 0, grid.shape[0] - 2)
    x0 = np.clip(gx.astype(int), 0, grid.shape[1] - 2)
    fy = (gy - y0)[:, None]
    fx = (gx - x0)[None, :]
    g = (grid[y0][:, x0] * (1 - fy) * (1 - fx) + grid[y0][:, x0 + 1] * (1 - fy) * fx
         + grid[y0 + 1][:, x0] * fy * (1 - fx) + grid[y0 + 1][:, x0 + 1] * fy * fx)
    return 128.0 / g


def preview(px, eeprom=None):
    p = px.astype(np.float32) - BLACK
    ch = [p[0::2, 0::2], p[0::2, 1::2], p[1::2, 0::2], p[1::2, 1::2]]
    if eeprom is not None:
        e = np.fromfile(eeprom, dtype=np.uint8)
        for i in range(4):
            grid = e[0x100 + 64 * i:0x100 + 64 * i + 63].reshape(7, 9).astype(np.float32)
            ch[i] = ch[i] * shading_gain(grid, *ch[i].shape)
    rgb = np.stack([ch[0], (ch[1] + ch[2]) / 2, ch[3]], -1)[::3, ::3]
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
        eeprom = sys.argv[4] if len(sys.argv) > 4 else None
        write_png(sys.argv[3], preview(unpack(fr[-1]), eeprom))


if __name__ == "__main__":
    main()
