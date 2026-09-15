#!/usr/bin/env python3
"""Drive a force-feedback device, to tell enumeration apart from working.

An ff-memless device appears in /dev/input whether or not a motor is actually
wired to the output it drives, so `pm8xxx_vib_ffmemless` showing up as event0
proves nothing on its own. The only test is to upload an effect and play it.

Run it on the phone - no compiler needed there, and none of this needs one:

    scp tools/ff-test.py mahan@<phone>:/tmp/
    ssh -t mahan@<phone> 'sudo python3 /tmp/ff-test.py'

The trap this exists to avoid: `sizeof(struct ff_effect)` is **44** on arm32,
not 40. `custom_len` in `ff_periodic_effect` is a `__u32`, so the union is 28
bytes on top of a 16-byte header (14 bytes of shorts, padded to 16 for the
union's 4-byte alignment). EVIOCSFF encodes that size in the ioctl number, so
getting it wrong does not fail cleanly - it returns EFAULT, which reads like a
driver bug rather than an arithmetic one.

pm8xxx-vibrator accepts FF_RUMBLE only, and takes its level from
`strong_magnitude >> 8`, so 0xffff is full scale and anything under 0x0100
rounds to a stop.
"""

import array
import ctypes
import fcntl
import os
import struct
import sys
import time

# _IOC(dir, type, nr, size), asm-generic layout - arm uses it.
def _IOC(d, t, nr, size):
    return (d << 30) | (size << 16) | (ord(t) << 8) | nr

_IOC_WRITE, _IOC_READ = 1, 2

FF_EFFECT_SIZE = 44          # arm32; see the module docstring
EVIOCSFF = _IOC(_IOC_WRITE, 'E', 0x80, FF_EFFECT_SIZE)
EVIOCRMFF = _IOC(_IOC_WRITE, 'E', 0x81, 4)

def EVIOCGNAME(n):
    return _IOC(_IOC_READ, 'E', 0x06, n)

def EVIOCGBIT(ev, n):
    return _IOC(_IOC_READ, 'E', 0x20 + ev, n)

EV_FF, FF_RUMBLE = 0x15, 0x50

# struct input_event is 16 bytes on arm32: the kernel side uses
# __kernel_ulong_t for sec/usec regardless of userspace's time_t width.
INPUT_EVENT = struct.Struct('<LLHHi')


def ff_effect(kind, effect_id, strong, weak, length_ms):
    """Pack struct ff_effect. Header is 16 bytes, union 28, total 44."""
    head = struct.pack('<HhHHHHH',
                       kind,          # type
                       effect_id,     # id, -1 asks the kernel to allocate
                       0,             # direction
                       0, 0,          # trigger.button, trigger.interval
                       length_ms, 0)  # replay.length, replay.delay
    head += b'\0' * (16 - len(head))            # pad to the union's alignment
    body = struct.pack('<HH', strong, weak)     # ff_rumble_effect
    body += b'\0' * (28 - len(body))
    blob = head + body
    assert len(blob) == FF_EFFECT_SIZE, len(blob)
    return bytearray(blob)


def find_device(match):
    for name in sorted(os.listdir('/dev/input')):
        if not name.startswith('event'):
            continue
        path = '/dev/input/' + name
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError as e:
            print(f'  {path}: {e.strerror}')
            continue
        buf = array.array('B', [0] * 128)
        fcntl.ioctl(fd, EVIOCGNAME(128), buf)
        dev = bytes(buf).split(b'\0')[0].decode('utf-8', 'replace')

        feat = array.array('B', [0] * 16)
        try:
            fcntl.ioctl(fd, EVIOCGBIT(EV_FF, 16), feat)
            has_rumble = bool(feat[FF_RUMBLE // 8] & (1 << (FF_RUMBLE % 8)))
        except OSError:
            has_rumble = False

        print(f'  {path}: {dev!r}{"  [FF_RUMBLE]" if has_rumble else ""}')
        if match in dev.lower() or (match == '' and has_rumble):
            return fd, path, dev, has_rumble
        os.close(fd)
    return None, None, None, False


def play(fd, strong, weak, seconds, label):
    eff = ff_effect(FF_RUMBLE, -1, strong, weak, int(seconds * 1000))
    try:
        fcntl.ioctl(fd, EVIOCSFF, eff, True)
    except OSError as e:
        print(f'  {label}: EVIOCSFF failed: {e}')
        if e.errno == 14:
            print('    EFAULT usually means the struct size is wrong for this arch.')
        return False
    eid = struct.unpack_from('<h', eff, 2)[0]
    print(f'  {label}: uploaded as effect id {eid}, playing {seconds}s ...')
    os.write(fd, INPUT_EVENT.pack(0, 0, EV_FF, eid, 1))
    time.sleep(seconds)
    os.write(fd, INPUT_EVENT.pack(0, 0, EV_FF, eid, 0))
    # EVIOCRMFF takes the effect id *by value* - the kernel casts the ioctl
    # argument itself to int - so handing it a packed buffer passes a pointer
    # and erases nothing, returning EINVAL.
    try:
        fcntl.ioctl(fd, EVIOCRMFF, eid)
    except OSError as e:
        print(f'    (EVIOCRMFF: {e})')
    return True


def main():
    match = sys.argv[1].lower() if len(sys.argv) > 1 else 'vib'
    print(f'struct ff_effect = {FF_EFFECT_SIZE} bytes, '
          f'EVIOCSFF = 0x{EVIOCSFF:08x}')
    print('Scanning /dev/input:')
    fd, path, dev, has_rumble = find_device(match)
    if fd is None:
        print(f'\nNo input device matching {match!r}. '
              'Is this the kernel with the vibrator enabled?')
        return 1

    print(f'\nUsing {path} ({dev})')
    if not has_rumble:
        print('  warning: this device does not advertise FF_RUMBLE')

    print('\nWatch and feel the phone - the point is whether the motor moves.')
    ok = True
    ok &= play(fd, 0xffff, 0, 1.0, 'full strength')
    time.sleep(0.5)
    ok &= play(fd, 0x4000, 0, 1.0, 'quarter strength')
    time.sleep(0.5)
    ok &= play(fd, 0, 0xffff, 1.0, 'weak magnitude only')

    print('\nThree bursts sent.' if ok else '\nSome uploads failed.')
    print('If nothing was felt but the uploads succeeded, the driver is fine '
          'and\nthe motor is not on this PMIC output.')
    os.close(fd)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
