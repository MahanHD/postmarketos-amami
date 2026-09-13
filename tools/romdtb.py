#!/usr/bin/env python3
"""Pull the downstream device tree out of a stock or LineageOS image, and read it.

This is how `kgsl_iommu`, `mdp_iommu`, the audio inventory, the camera bindings and
the `batt_therm` scaling were all recovered without any vendor source. `dtc` is not
needed and is not installed.

**Prefer stock over LineageOS where it matters.** Lineage descends from Sony's GPL
tree but drifts; stock pairs with the TrustZone image the phone actually boots. For
the two IOMMU nodes they turned out to agree exactly - but that was worth checking,
not assuming.

**And neither is the final authority - the hardware is.** Stock lists SPI 241 for all
three GPU context banks, which is only right for whichever one lands on IRPTNDX 1.
Use the tree to find candidates, then confirm on the device.

Extracting:

  LineageOS: boot.img sits in the zip, and the QCDT follows the ramdisk.
      unzip -p lineage-*.zip boot.img > boot.img
      romdtb.py extract boot.img -o dtb/

  Stock: the download is a zip holding an .ftf, which is itself a zip of .sin files.
      unzip -p D5503_*.zip '*.ftf' > fw.ftf
      unzip -p fw.ftf kernel.sin > kernel.sin
      romdtb.py extract kernel.sin -o dtb/

  A .sin starts with \\x03SIN and a big-endian header length (1824 here); the payload
  is Sony's MMCF container, not a raw boot image, so this just finds the QCDT inside
  rather than parsing MMCF.

Reading:

      romdtb.py show dtb/dtb-0.dtb iommu
      romdtb.py show dtb/dtb-0.dtb fd928000
"""

import argparse
import os
import struct
import sys


class FDT:
    def __init__(self, data):
        (magic, _total, off_struct, off_strings,
         _off_rsv, _ver, _last, _boot, size_str, size_struct) = struct.unpack(">10I", data[:40])
        if magic != 0xD00DFEED:
            raise ValueError("not a dtb (magic %#x)" % magic)
        self.struct = data[off_struct:off_struct + size_struct]
        self.strings = data[off_strings:off_strings + size_str]

    def _str(self, off):
        return self.strings[off:self.strings.index(b"\0", off)].decode()

    def nodes(self):
        """Return {path: {prop: bytes}}."""
        out, path, b, i = {}, [], self.struct, 0
        while i < len(b):
            tok = struct.unpack(">I", b[i:i + 4])[0]
            i += 4
            if tok == 1:                                  # BEGIN_NODE
                end = b.index(b"\0", i)
                path.append(b[i:end].decode())
                i = (end + 4) & ~3
                out.setdefault("/".join(path), {})
            elif tok == 2:                                # END_NODE
                path.pop()
            elif tok == 3:                                # PROP
                ln, nameoff = struct.unpack(">II", b[i:i + 8])
                i += 8
                out["/".join(path)][self._str(nameoff)] = b[i:i + ln]
                i = (i + ln + 3) & ~3
            elif tok == 4:                                # NOP
                pass
            elif tok == 9:                                # END
                break
            else:
                raise ValueError("bad token %d at %d" % (tok, i))
        return out


def cells(v):
    return list(struct.unpack(">%dI" % (len(v) // 4), v[:len(v) // 4 * 4]))


def as_text(v):
    return v.replace(b"\0", b" ").decode(errors="replace").strip()


NUMERIC = ("reg", "interrupts", "qcom,iommu-ctx-sids", "qcom,iommu-secure-id",
           "qcom,iommu-bfb-regs", "qcom,iommu-bfb-data", "qcom,scale-function",
           "#address-cells", "#size-cells", "#iommu-cells", "#global-interrupts")
TEXT = ("compatible", "label", "status", "clock-names", "reg-names")


def cmd_extract(args):
    data = open(args.image, "rb").read()
    pos = data.find(b"QCDT")
    if pos < 0:
        raise SystemExit("no QCDT container found in %s" % args.image)
    dt = data[pos:]
    ver, ndev = struct.unpack("<II", dt[4:12])
    esz = {1: 20, 2: 24, 3: 28}.get(ver)
    if not esz:
        raise SystemExit("unknown QCDT version %d" % ver)
    print("QCDT v%d, %d entries at offset %d" % (ver, ndev, pos))
    os.makedirs(args.outdir, exist_ok=True)
    seen = {}
    for i in range(ndev):
        vals = struct.unpack("<%dI" % (esz // 4), dt[12 + i * esz: 12 + (i + 1) * esz])
        off, size = vals[-2], vals[-1]
        if off in seen:
            print("  entry %d ids=%s -> same blob as %s" % (i, vals[:-2], seen[off]))
            continue
        blob = dt[off:off + size]
        if blob[:4] != b"\xd0\x0d\xfe\xed":
            print("  entry %d ids=%s -> not a dtb, skipped" % (i, vals[:-2]))
            continue
        name = os.path.join(args.outdir, "dtb-%d.dtb" % i)
        open(name, "wb").write(blob)
        seen[off] = name
        print("  entry %d ids=%s -> %s (%d bytes)" % (i, vals[:-2], name, size))


def cmd_show(args):
    nodes = FDT(open(args.dtb, "rb").read()).nodes()
    needle = args.match.lower()
    for path in sorted(nodes):
        props = nodes[path]
        hay = (path + " " + as_text(props.get("compatible", b""))).lower()
        if needle not in hay:
            continue
        print("NODE %s" % path)
        for k, v in sorted(props.items()):
            if k in TEXT:
                print("   %-28s %s" % (k, as_text(v)))
            elif k in NUMERIC and len(v) % 4 == 0 and v:
                print("   %-28s %s" % (k, " ".join(hex(c) for c in cells(v))))
            elif not v:
                print("   %-28s (empty / boolean)" % k)
            else:
                print("   %-28s (%d bytes)" % (k, len(v)))
        print()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="pull dtbs out of a boot image or kernel.sin")
    e.add_argument("image")
    e.add_argument("-o", "--outdir", default="dtb")
    e.set_defaults(func=cmd_extract)

    s = sub.add_parser("show", help="print nodes whose path or compatible matches")
    s.add_argument("dtb")
    s.add_argument("match")
    s.set_defaults(func=cmd_show)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
