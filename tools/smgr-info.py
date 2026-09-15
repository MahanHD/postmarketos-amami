#!/usr/bin/env python3
"""Ask SMGR what each data type of a sensor actually is."""
import socket, struct, sys, time
sys.path.insert(0, '/tmp')
AF_QIPCRTR = 42
NODE, PORT = 5, 6

def tlv(t, p): return struct.pack('<BH', t, len(p)) + p
def parse_tlvs(b):
    o, i = {}, 0
    while i + 3 <= len(b):
        t, ln = struct.unpack_from('<BH', b, i); o[t] = b[i+3:i+3+ln]; i += 3 + ln
    return o

s = socket.socket(AF_QIPCRTR, socket.SOCK_DGRAM, 0)
for c in (1, 0, 3, 5):
    try: s.bind((c, 0)); break
    except OSError: pass
s.settimeout(3.0)

sid = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x28
body = tlv(0x01, struct.pack('<B', sid))
s.sendto(struct.pack('<BHHH', 0, 77, 0x06, len(body)) + body, (NODE, PORT))
t0 = time.time()
r = None
while time.time() - t0 < 3:
    d, _ = s.recvfrom(8192)
    typ, txn, msg, ln = struct.unpack_from('<BHHH', d, 0)
    if typ == 2 and txn == 77:
        r = parse_tlvs(d[7:7+ln]); break
if r is None:
    print('no response'); sys.exit(1)

print(f'sensor 0x{sid:02x}')
blob = r.get(0x03, b'')
if blob:
    n = blob[0]; i = 1
    for k in range(n):
        s_id = blob[i]; dt = blob[i+1]; i += 2
        nl = blob[i]; name = blob[i+1:i+1+nl].decode('ascii','replace'); i += 1+nl
        vl = blob[i]; vend = blob[i+1:i+1+vl].decode('ascii','replace'); i += 1+vl
        val1, maxrate, val2, cur_ua, rng, res = struct.unpack_from('<IHHHII', blob, i)
        i += 18
        print(f'  data_type {dt}: {vend} {name}')
        print(f'      max_sample_rate={maxrate}Hz  current={cur_ua}uA '
              f'range={rng} resolution={res} val1={val1} val2={val2}')
for t, lbl in ((0x13, 'native_sample_rates'),):
    if t in r:
        b = r[t]; cnt = b[0]; i = 1
        for k in range(cnt):
            rc = b[i]; i += 1
            rates = struct.unpack_from('<' + 'H'*rc, b, i); i += 2*rc
            print(f'  {lbl}[{k}]: {list(rates)}')
