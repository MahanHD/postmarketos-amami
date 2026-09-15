#!/usr/bin/env python3
"""List every QMI service advertised over QRTR, and prove the probe works first.

The SLIMbus NGD controller does nothing until the ADSP advertises QMI service
0x301, and it waits *silently* - so an empty /sys/bus/slimbus/devices with a
silent dmesg cannot by itself tell "the service is missing" from "the driver is
broken". This asks the router directly.

It self-tests before reporting, by publishing a fake service and checking the
lookup finds it. There is no known-good QMI service on this phone to validate
against - wcn36xx talks WCNSS_CTRL over SMD, not QMI - so without that step a
zero would be worthless. It already was once: an earlier version of this script
guessed the command numbers, sent HELLO and RESUME_TX instead of NEW_SERVER and
NEW_LOOKUP, and reported a confident zero.
"""
import socket, struct, sys, time

AF_QIPCRTR = 42
QRTR_PORT_CTRL = 0xfffffffe
# include/uapi/linux/qrtr.h - do not guess these
QRTR_TYPE_NEW_SERVER = 4
QRTR_TYPE_DEL_SERVER = 5
QRTR_TYPE_NEW_LOOKUP = 10
FAKE_SVC, FAKE_INST = 0x4242, 1
KNOWN = {0x301: '<-- SLIMbus, what the NGD controller waits for'}


def bind_local(s):
    """qrtr_bind() rejects any node but the local one, so 0 is not a wildcard."""
    for cand in (1, 0, 3, 5):
        try:
            s.bind((cand, 0))
            return s.getsockname()
        except OSError:
            continue
    raise SystemExit('cannot bind a qrtr socket - is qrtr loaded?')


def lookup(node, service=0, instance=0, secs=2.5):
    """Ask the name service for matching servers.

    The listing ends with an all-zero NEW_SERVER as a terminator, so receiving
    only that means "the list really is empty" - which is a different fact from
    receiving nothing at all.
    """
    s = socket.socket(AF_QIPCRTR, socket.SOCK_DGRAM, 0)
    bind_local(s)
    s.settimeout(0.4)
    s.sendto(struct.pack('<IIIII', QRTR_TYPE_NEW_LOOKUP, service, instance, 0, 0),
             (node, QRTR_PORT_CTRL))
    found, terminated, t0 = set(), False, time.time()
    while time.time() - t0 < secs:
        try:
            data, _ = s.recvfrom(4096)
        except socket.timeout:
            continue
        if len(data) < 20:
            continue
        cmd, svc, inst, n, p = struct.unpack('<IIIII', data[:20])
        if cmd != QRTR_TYPE_NEW_SERVER:
            continue
        if svc == 0 and inst == 0 and n == 0 and p == 0:
            terminated = True
        else:
            found.add((n, svc, inst, p))
    return found, terminated


def main():
    pub = socket.socket(AF_QIPCRTR, socket.SOCK_DGRAM, 0)
    node, port = bind_local(pub)
    pub.sendto(struct.pack('<IIIII', QRTR_TYPE_NEW_SERVER,
                           FAKE_SVC, FAKE_INST, node, port),
               (node, QRTR_PORT_CTRL))
    time.sleep(0.4)
    found, terminated = lookup(node)
    ok = any(v[1] == FAKE_SVC for v in found)
    pub.sendto(struct.pack('<IIIII', QRTR_TYPE_DEL_SERVER,
                           FAKE_SVC, FAKE_INST, node, port),
               (node, QRTR_PORT_CTRL))

    print(f'local node {node}')
    print(f'self-test: published 0x{FAKE_SVC:04x} and the lookup '
          f'{"found it - probe works" if ok else "did NOT find it - PROBE BROKEN"}')
    if not terminated and not found:
        print('           no end-of-listing terminator either: no reply at all')
    if not ok:
        return 1

    real = sorted(v for v in found if v[1] != FAKE_SVC)
    print(f'\n{len(real)} real service(s):')
    for n, svc, inst, p in real:
        print(f'  node {n:<3} service 0x{svc:04x} v{inst & 0xff} '
              f'inst {inst >> 8:<3} port {p:<12} {KNOWN.get(svc, "")}')
    print('\nSLIMbus 0x301 IS advertised' if any(v[1] == 0x301 for v in real)
          else '\nSLIMbus 0x301 is NOT advertised')
    return 0


sys.exit(main())
