#!/usr/bin/env python3
"""Clean SMGR trial: every indication filtered by report_id, and a settle after
each DELETE so a previous sensor's stragglers cannot be counted as this one's."""
import socket, struct, sys, time
AF_QIPCRTR = 42
NODE, PORT = 5, 6
TICKS = 32768

def tlv(t, p): return struct.pack('<BH', t, len(p)) + p
def parse_tlvs(b):
    o, i = {}, 0
    while i + 3 <= len(b):
        t, ln = struct.unpack_from('<BH', b, i); o[t] = b[i+3:i+3+ln]; i += 3+ln
    return o

s = socket.socket(AF_QIPCRTR, socket.SOCK_DGRAM, 0)
for c in (1, 0, 3, 5):
    try: s.bind((c, 0)); break
    except OSError: pass
s.settimeout(0.3)
txn = [1]

def send(msg, body):
    t = txn[0]; txn[0] = (t + 1) & 0xffff
    s.sendto(struct.pack('<BHHH', 0, t, msg, len(body)) + body, (NODE, PORT))
    return t

def buffering(rid, items, rr, action=1):
    body = tlv(0x01, struct.pack('<B', rid)) + tlv(0x02, struct.pack('<B', action))
    body += tlv(0x03, struct.pack('<I', rr))
    p = struct.pack('<B', len(items))
    for it in items: p += struct.pack('<BBHHH', *it)
    body += tlv(0x04, p)
    return send(0x21, body)

def drain(secs):
    t0 = time.time()
    while time.time() - t0 < secs:
        try: s.recvfrom(8192)
        except socket.timeout: pass

def collect(rid, secs):
    """Count indications for THIS report_id only."""
    mine, other, t0, samples = 0, 0, time.time(), []
    resp = None
    while time.time() - t0 < secs:
        try: d, _ = s.recvfrom(8192)
        except socket.timeout: continue
        if len(d) < 7: continue
        typ, rtxn, msg, ln = struct.unpack_from('<BHHH', d, 0)
        t = parse_tlvs(d[7:7+ln])
        if typ == 2:
            resp = (struct.unpack_from('<H', t[0x02])[0] if 0x02 in t else None,
                    t[0x11][0] if 0x11 in t else None)
            continue
        if typ != 4 or msg != 0x22: continue
        got = t.get(0x01, b'\xff')[0]
        if got != rid:
            other += 1; continue
        mine += 1
        blob = t.get(0x03, b'')
        if blob and blob[0]:
            for k in range(blob[0]):
                off = 1 + k*16
                if off+16 <= len(blob):
                    samples.append(struct.unpack_from('<III', blob, off))
    return resp, mine, other, samples

def trial(tag, rid, items, rate, secs):
    buffering(rid, items, rate * TICKS * 2)
    resp, mine, other, samples = collect(rid, secs)
    uniq = sorted(set(samples))
    print(f'{tag}')
    print(f'   resp result={resp[0] if resp else "-"} ack_nak={resp[1] if resp else "-"}'
          f'   indications(mine)={mine}  (other report_ids seen: {other})')
    if samples:
        print(f'   {len(samples)} samples, {len(uniq)} distinct; first 4: {samples[:4]}')
    buffering(rid, [], 0, action=2)
    drain(2.0)

print('CONTROL: accelerometer 0x00 @50Hz for 4s')
trial('  accel', 0x00, [(0x00, 0, 3, 50, 1)], 50, 4)
print()
print('PROXIMITY 0x28 data_type 0 (12.7mA IR LED), 12s each')
trial('  val1=3 val2=1 (what the driver sends)', 0x28, [(0x28, 0, 3, 5, 1)], 5, 12)
trial('  val1=2 val2=4 (what SINGLE_SENSOR_INFO reports)', 0x28, [(0x28, 0, 2, 5, 4)], 5, 12)
print()
print('AMBIENT LIGHT 0x28 data_type 1 (175uA), 12s')
trial('  val1=3 val2=1', 0x28, [(0x28, 1, 3, 5, 1)], 5, 12)
