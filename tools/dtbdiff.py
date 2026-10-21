#!/usr/bin/env python3
"""Property-level difference between two flattened device trees.

  dtbdiff.py old.dtb new.dtb

Prints each property that was added, removed or changed, by node path, so a
device tree change can be checked against what it was meant to change.
dtc is not needed. Values print as 32-bit cells when they divide evenly,
as text when they look like strings, and as hex otherwise.
"""
import struct
import sys

from romdtb import FDT


def props(path):
    """{"node/path:property": value} for every property in the blob."""
    fdt = FDT(open(path, "rb").read())
    return {"%s:%s" % (node, name): value
            for node, ps in fdt.nodes().items() for name, value in ps.items()}


def show(v):
    if v and v[-1:] == b'\0' and all(32 <= c < 127 or c == 0 for c in v):
        return repr(v.decode().rstrip('\0').replace('\0', '", "'))
    if len(v) % 4 == 0:
        return '<' + ' '.join('%#x' % c for c in struct.unpack('>%dI' % (len(v) // 4), v)) + '>'
    return v.hex()


old, new = props(sys.argv[1]), props(sys.argv[2])
for key in sorted(set(old) | set(new)):
    if key not in new:
        print('- %s = %s' % (key, show(old[key])))
    elif key not in old:
        print('+ %s = %s' % (key, show(new[key])))
    elif old[key] != new[key]:
        print('~ %s: %s -> %s' % (key, show(old[key]), show(new[key])))
