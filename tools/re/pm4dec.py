"""Decode an a3xx PM4 command stream (a list of dwords) with Mesa's register names.

Set MESA_REGS to the src/freedreno/registers/adreno/ directory of a Mesa tree.
"""
import os
import xml.etree.ElementTree as ET

REGDIR = os.environ.get("MESA_REGS", "")


def _strip(tag):
    return tag.split('}')[-1]


def load_regs():
    regs = {}
    root = ET.parse(os.path.join(REGDIR, "a3xx.xml")).getroot()
    for dom in root.iter():
        if _strip(dom.tag) == "domain" and dom.get("name") == "A3XX":
            break

    def walk(node, base, prefix):
        for c in node:
            t = _strip(c.tag)
            if t in ("reg32", "reg64"):
                regs[base + int(c.get("offset"), 0)] = prefix + c.get("name")
            elif t == "array":
                off = int(c.get("offset"), 0)
                stride = int(c.get("stride"), 0)
                ln = int(c.get("length"), 0)
                for i in range(ln):
                    walk(c, off + i * stride, "%s%s[%d]." % (prefix, c.get("name"), i))
    walk(dom, 0, "")
    ops = {}
    pm4 = ET.parse(os.path.join(REGDIR, "adreno_pm4.xml")).getroot()
    for e in pm4.iter():
        if _strip(e.tag) == "enum" and e.get("name") == "adreno_pm4_type3_packets":
            for v in e:
                if _strip(v.tag) == "value":
                    var = v.get("variants") or "A3XX"
                    if "A2XX" in var or "A3XX" in var or var.startswith("A3"):
                        ops.setdefault(int(v.get("value"), 0), v.get("name"))
    return regs, ops


REGS, OPS = load_regs()


def decode(dw, out=print):
    i = 0
    while i < len(dw):
        h = dw[i]
        t = h >> 30
        if t == 0:
            reg = h & 0x7fff
            n = ((h >> 16) & 0x3fff) + 1
            for k in range(n):
                r = reg + k
                out("  %04x %-36s = 0x%08x" % (r, REGS.get(r, "?"), dw[i + 1 + k] if i + 1 + k < len(dw) else 0))
            i += 1 + n
        elif t == 3:
            op = (h >> 8) & 0xff
            n = ((h >> 16) & 0x3fff) + 1
            out("  %s (0x%02x): %s" % (OPS.get(op, "?"), op, " ".join("%08x" % x for x in dw[i + 1:i + 1 + n])))
            i += 1 + n
        elif t == 2:
            out("  nop")
            i += 1
        else:
            out("  ?? %08x" % h)
            i += 1
