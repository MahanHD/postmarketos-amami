#!/usr/bin/env python3
"""Does a new msm GEM buffer start zeroed?

Run on the phone. Fills a buffer with 0xa5, frees it, allocates one of the same
size again and counts non-zero bytes. On the VRAM carveout the new buffer
usually lands on the pages just freed, so before 0106 it came back full of
0xa5; with 0106 it must be all zeroes."""
import fcntl, mmap, os, struct

def IOWR(nr, size): return (3 << 30) | (size << 16) | (ord('d') << 8) | nr
def IOW(nr, size): return (1 << 30) | (size << 16) | (ord('d') << 8) | nr
GEM_NEW = IOWR(0x40 + 0x02, 16)      # struct drm_msm_gem_new
GEM_INFO = IOWR(0x40 + 0x03, 24)     # struct drm_msm_gem_info
GEM_CLOSE = IOW(0x09, 8)             # struct drm_gem_close
MSM_BO_WC, MSM_BO_CACHED, INFO_GET_OFFSET = 0x20000, 0x10000, 0

fd = os.open("/dev/dri/renderD128", os.O_RDWR)

def new(size, flags):
    b = bytearray(struct.pack("<QII", size, flags, 0))
    fcntl.ioctl(fd, GEM_NEW, b)
    return struct.unpack("<QII", b)[2]

def mapped(handle, size):
    b = bytearray(struct.pack("<IIQII", handle, INFO_GET_OFFSET, 0, 0, 0))
    fcntl.ioctl(fd, GEM_INFO, b)
    off = struct.unpack("<IIQII", b)[2]
    return mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=off)

def close(handle):
    fcntl.ioctl(fd, GEM_CLOSE, struct.pack("<II", handle, 0))

for name, flags in (("WC", MSM_BO_WC), ("cached", MSM_BO_CACHED)):
    for size in (4096, 1 << 20, 4 << 20):
        h = new(size, flags)
        m = mapped(h, size); m[:] = b"\xa5" * size; m.close(); close(h)
        h = new(size, flags)
        m = mapped(h, size); data = m[:]; m.close(); close(h)
        nz = size - data.count(0)
        print("%-6s %7d bytes: %7d non-zero, %d of them 0xa5" % (name, size, nz, data.count(0xa5)))
