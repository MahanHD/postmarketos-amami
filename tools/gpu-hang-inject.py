#!/usr/bin/env python3
"""Hang the GPU on purpose, then check that recovery really worked.

  gpu-hang-inject.py [wait|fault|none] [rounds]

Run on the phone. Each round submits one job that cannot finish, then a canary
job from a second file descriptor that only writes a counter to memory, and
waits for the counter to land. A canary that never lands means the reset left
the GPU unable to run anything.

  wait   the CP waits for a memory value that never comes (CP_WAIT_REG_MEM)
  fault  the CP jumps to an indirect buffer at an unmapped GPU address
  none   no hang, only the canary (the control)
"""
import fcntl, mmap, os, struct, sys, time

def IOWR(nr, size): return (3 << 30) | (size << 16) | (ord('d') << 8) | nr
def IOW(nr, size): return (1 << 30) | (size << 16) | (ord('d') << 8) | nr
GEM_NEW = IOWR(0x40 + 0x02, 16)      # struct drm_msm_gem_new
GEM_INFO = IOWR(0x40 + 0x03, 24)     # struct drm_msm_gem_info
GEM_SUBMIT = IOWR(0x40 + 0x06, 72)   # struct drm_msm_gem_submit
GEM_CLOSE = IOW(0x09, 8)             # struct drm_gem_close
MSM_BO_WC = 0x20000
INFO_GET_OFFSET, INFO_GET_IOVA = 0, 1
PIPE_3D0, CMD_BUF = 0x10, 1
BO_READ, BO_WRITE = 1, 2

CP_INDIRECT_BUFFER_PFD, CP_WAIT_REG_MEM, CP_MEM_WRITE = 0x37, 0x3c, 0x3d

def pkt3(op, *words):
    return [(3 << 30) | ((len(words) - 1) << 16) | (op << 8)] + list(words)


class Gpu:
    def __init__(self):
        self.fd = os.open("/dev/dri/renderD128", os.O_RDWR)

    def new(self, size):
        b = bytearray(struct.pack("<QII", size, MSM_BO_WC, 0))
        fcntl.ioctl(self.fd, GEM_NEW, b)
        return struct.unpack("<QII", b)[2]

    def info(self, handle, what):
        b = bytearray(struct.pack("<IIQII", handle, what, 0, 0, 0))
        fcntl.ioctl(self.fd, GEM_INFO, b)
        return struct.unpack("<IIQII", b)[2]

    def map(self, handle, size):
        return mmap.mmap(self.fd, size, mmap.MAP_SHARED,
                         mmap.PROT_READ | mmap.PROT_WRITE,
                         offset=self.info(handle, INFO_GET_OFFSET))

    def submit(self, cmd_handle, nwords, data_handle):
        bos = struct.pack("<IIQ", BO_READ, cmd_handle, 0)
        bos += struct.pack("<IIQ", BO_READ | BO_WRITE, data_handle, 0)
        cmds = struct.pack("<IIIIIIQ", CMD_BUF, 0, 0, nwords * 4, 0, 0, 0)
        bbuf, cbuf = bytearray(bos), bytearray(cmds)
        bp = ctypes_addr(bbuf)
        cp = ctypes_addr(cbuf)
        b = bytearray(struct.pack("<IIIIQQiIQQIIII", PIPE_3D0, 0, 2, 1, bp, cp,
                                  -1, 0, 0, 0, 0, 0, 0, 0))
        fcntl.ioctl(self.fd, GEM_SUBMIT, b)
        return struct.unpack_from("<I", b, 4)[0]


def ctypes_addr(buf):
    import ctypes
    c = (ctypes.c_char * len(buf)).from_buffer(buf)
    ctypes_addr.keep.append(c)
    return ctypes.addressof(c)
ctypes_addr.keep = []


def hang_job(gpu, mode):
    data = gpu.new(4096)
    addr = gpu.info(data, INFO_GET_IOVA)
    if mode == "wait":
        # function 3 (equal), memory space: wait for 0x1234 where there is 0
        words = pkt3(CP_WAIT_REG_MEM, 0x13, addr, 0x1234, 0xffffffff, 16)
    else:
        words = pkt3(CP_INDIRECT_BUFFER_PFD, 0xdead0000, 64)
    cmd = gpu.new(4096)
    m = gpu.map(cmd, 4096)
    m[:len(words) * 4] = struct.pack("<%dI" % len(words), *words)
    m.close()
    return gpu.submit(cmd, len(words), data)


def canary(gpu, value, timeout):
    data = gpu.new(4096)
    out = gpu.map(data, 4096)
    words = pkt3(CP_MEM_WRITE, gpu.info(data, INFO_GET_IOVA), value)
    cmd = gpu.new(4096)
    m = gpu.map(cmd, 4096)
    m[:len(words) * 4] = struct.pack("<%dI" % len(words), *words)
    m.close()
    gpu.submit(cmd, len(words), data)
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if struct.unpack_from("<I", out, 0)[0] == value:
            return time.monotonic() - t0
        time.sleep(0.02)
    return None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "wait"
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    bad = 0
    for i in range(rounds):
        hanger, checker = Gpu(), Gpu()
        if mode != "none":
            hang_job(hanger, mode)
        t = canary(checker, 0xc0de0000 + i, 15)
        if t is None:
            bad += 1
        print("%s round %d: canary %s" % (time.strftime("%T"), i + 1,
              "MISSING" if t is None else "after %.2f s" % t), flush=True)
        os.close(hanger.fd)
        os.close(checker.fd)
    print("done, %d of %d canaries missing" % (bad, rounds))


if __name__ == "__main__":
    main()
