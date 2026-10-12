"""Print the summary of an msm devcoredump and decode its ringbuffer as PM4.

  MESA_REGS=<mesa>/src/freedreno/registers/adreno devcore-ring.py dump.devcore [dwords]

Without a dword count it decodes up to the ring's wptr. Uses pm4dec.py for the
register and opcode names.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm4dec  # noqa: E402


def ascii85(text):
    """Decode the devcoredump flavour of ascii85: 'z' is four zero bytes."""
    text = re.sub(r"\s", "", text)
    out = bytearray()
    group = []
    for c in text:
        if c == "z" and not group:
            out += b"\0" * 4
            continue
        group.append(ord(c) - 33)
        if len(group) == 5:
            v = 0
            for g in group:
                v = v * 85 + g
            out += struct.pack("<I", v & 0xffffffff)
            group = []
    return bytes(out)


def main():
    txt = open(sys.argv[1]).read()
    for key in ("comm", "rbbm-status", "last-fence", "retired-fence", "rptr", "wptr"):
        m = re.search(r"^\s*%s: (.*)$" % key, txt, re.M)
        if m:
            print("%-14s %s" % (key, m.group(1)))
    m = re.search(r"ringbuffer:.*?data: !!ascii85 \|\n((?:     .*\n)+)", txt, re.S)
    data = ascii85(m.group(1))
    words = list(struct.unpack("<%dI" % (len(data) // 4), data))
    wptr = int(re.search(r"^\s*wptr: (\d+)", txt, re.M).group(1))
    n = int(sys.argv[2]) if len(sys.argv) > 2 else wptr
    print("--- ring, %d dwords" % n)
    pm4dec.decode(words[:n])


if __name__ == "__main__":
    main()
