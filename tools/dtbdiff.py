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


def props(path):
    b = open(path, 'rb').read()
    magic, _, off_struct, off_strings = struct.unpack('>IIII', b[:16])
    if magic != 0xd00dfeed:
        sys.exit('%s: not a flattened device tree' % path)
    strings = b[off_strings:]
    out, stack, p = {}, [], off_struct
    while True:
        tag, = struct.unpack('>I', b[p:p + 4])
        p += 4
        if tag == 1:
            end = b.index(b'\0', p)
            stack.append(b[p:end].decode())
            p = (end + 4) & ~3
        elif tag == 2:
            stack.pop()
        elif tag == 3:
            size, name_off = struct.unpack('>II', b[p:p + 8])
            p += 8
            name = strings[name_off:strings.index(b'\0', name_off)].decode()
            out['/'.join(stack[1:]) + ':' + name] = b[p:p + size]
            p = (p + size + 3) & ~3
        elif tag == 9:
            return out


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
