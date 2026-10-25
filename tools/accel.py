#!/usr/bin/env python3
"""accel.py: read ~2 s of the qcom-smgr accelerometer buffer, print the mean |g| in m/s^2."""
import glob, os, struct, time, math
dev = next((d for d in glob.glob('/sys/bus/iio/devices/iio:device*')
            if open(d + '/name').read().strip() == 'qcom-smgr-accel'), None)
if not dev:
    print('accel: not enumerated'); raise SystemExit
se = dev + '/scan_elements'
chans = []
for en in sorted(glob.glob(se + '/*_en')):
    open(en, 'w').write('1')
    base = en[:-3]
    t = open(base + '_type').read().strip()          # e.g. le:s32/32>>0
    idx = int(open(base + '_index').read())
    bits = int(t.split('/')[1].split('>>')[0])
    chans.append((idx, os.path.basename(base), bits // 8, t.split(':')[1][0] == 's'))
chans.sort()
scale = float(open(dev + '/in_accel_scale').read()) if os.path.exists(dev + '/in_accel_scale') else 1.0
open(dev + '/buffer/enable', 'w').write('1')
fd = os.open('/dev/' + os.path.basename(dev), os.O_RDONLY | os.O_NONBLOCK)
data = b''; end = time.time() + 2
while time.time() < end:
    try: data += os.read(fd, 4096)
    except BlockingIOError: time.sleep(0.05)
open(dev + '/buffer/enable', 'w').write('0')
# record layout: each channel aligned to its own size
off = 0; layout = []
for idx, name, size, signed in chans:
    off = (off + size - 1) // size * size; layout.append((name, off, size, signed)); off += size
rec = (off + 7) // 8 * 8 if any(s == 8 for _, _, s, _ in layout) else off
mags = []
for i in range(0, len(data) - rec + 1, rec):
    v = {n: int.from_bytes(data[i + o:i + o + s], 'little', signed=sg) for n, o, s, sg in layout}
    xyz = [v[k] * scale for k in sorted(v) if k.startswith('in_accel_') and k[-1] in 'xyz']
    if len(xyz) == 3: mags.append(math.sqrt(sum(a * a for a in xyz)))
print('accel: %d samples, mean |g| = %s' % (len(mags), '%.2f' % (sum(mags) / len(mags)) if mags else 'n/a'))
