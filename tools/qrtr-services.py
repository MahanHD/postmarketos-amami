#!/usr/bin/env python3
"""List every QMI service advertised on QRTR, by node.

The SLIMbus NGD controller does nothing until the ADSP advertises QMI service
0x301, and it waits silently - so "no slimbus devices and no dmesg" cannot by
itself tell "the service is missing" from "the driver is broken". This asks the
router directly: send a NEW_LOOKUP for every service to the control port and
print the NEW_SERVER replies.
"""
import socket, struct, time

AF_QIPCRTR = 42
QRTR_PORT_CTRL = 0xfffffffe
QRTR_TYPE_NEW_SERVER = 2
QRTR_TYPE_NEW_LOOKUP = 7
KNOWN = {0x301: '<-- SLIMbus, what the NGD controller waits for'}

s = socket.socket(AF_QIPCRTR, socket.SOCK_DGRAM, 0)
# qrtr_bind() rejects any node but the local one, so 0 is not a wildcard here.
# The in-kernel name service uses node 1 for the local processor.
for cand in (1, 0, 3, 5):
    try:
        s.bind((cand, 0))
        break
    except OSError:
        continue
local_node, local_port = s.getsockname()
print(f'local qrtr node {local_node}, port {local_port}')
s.settimeout(0.5)
# The lookup goes to the control port of our OWN node; the router answers with
# one NEW_SERVER per known service, from every node it can see.
s.sendto(struct.pack('<IIIII', QRTR_TYPE_NEW_LOOKUP, 0, 0, 0, 0),
         (local_node, QRTR_PORT_CTRL))

seen, t0 = set(), time.time()
while time.time() - t0 < 3.0:
    try:
        data, _ = s.recvfrom(4096)
    except socket.timeout:
        continue
    if len(data) < 20:
        continue
    cmd, svc, inst, node, port = struct.unpack('<IIIII', data[:20])
    if cmd == QRTR_TYPE_NEW_SERVER and svc:
        seen.add((node, svc, inst, port))

for node, svc, inst, port in sorted(seen):
    print(f'  node {node:<3} service 0x{svc:04x} '
          f'v{inst & 0xff} inst {inst >> 8:<3} port {port:<12} {KNOWN.get(svc, "")}')
print(f'\n{len(seen)} services total')
print('SLIMbus 0x301 IS advertised' if any(v[1] == 0x301 for v in seen)
      else 'SLIMbus 0x301 is NOT advertised by any node')
