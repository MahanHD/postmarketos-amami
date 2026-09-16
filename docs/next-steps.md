# Next steps

Rewritten 2026-09-12, after a long session that fixed a core-wedging bug of our own
making, produced the first power numbers, and then solved the GPU IOMMU.

The headline change since the last version: **the GPU IOMMU works**, and the thing
that cracked it was not another build. Five rebuild-and-guess cycles had failed;
reading the SMMU's own registers on a running phone through `/dev/mem` found both
bugs in one sitting. Prefer instrumenting the hardware over rebuilding it.

## Start here

**Device state: r90 is flashed and running** (`uname -v` = `#91`), verified by
readback. It is r87 plus the WCD9320 codec driver (`0049`), its DT node (`0050`)
and the sound card (`0050`/`0051`). **The codec is blacklisted** in
`/etc/modprobe.d/wcd9320-test.conf` because loading it oopses while building the
card - see Phase 3. Everything else is unaffected. All five sensors - accel, gyro, mag, proximity
and light - work when enabled on their own. Nothing is half-applied, and the
recipe, the flash and `/lib/modules` all agree at r87.

**Note the ADSP can lose a probe race at boot.** `qcom_smgr` has been seen to fail
once with `Failed to get available sensors: -ETIMEDOUT`, or with
`Single sensor info request failed: 0x701` on one sensor ID, and then succeed on
the retry. It is transient and not caused by any patch here - check
`/sys/bus/iio/devices/` before assuming a build broke the sensors.

**Mind the numbering: `pkgrel` + 1 is what `uname -v` prints.** r84 reports `#85`
and r85 reports `#86`, which is an easy way to think you booted the wrong thing.

r84 (`#85`) remains the fallback worth keeping - it is the last build whose every
feature was tested - and its image is still at
`boot-images/boot-r84.img`, md5 `d4550bf58700118ce0b3ee31aee67999`.

    boot partition:  /dev/disk/by-partlabel/boot  ->  mmcblk0p14  (20971520 bytes)
    r90, flashed now:  c2f94594ff341f68e5a1ce5aa04a1abd  (18231296 bytes)
    r87:               af83015f25d1851e2a7f3f7e1cae0ff7  (18229248 bytes)
    r86:               5091ea7c372c07b89b5db95f14cf14dc  (18225152 bytes)
    r85:               a9bb0fcb4c1b0e9624fbb6ff8bf3f48b  (18225152 bytes)
    r84:               d4550bf58700118ce0b3ee31aee67999  (18219008 bytes)
    r56:               69b89a70e0a216cc128579bea40f5561  (18153472 bytes)
    all three images kept in ~/Devices/Xperia-Z1-Compact/boot-images/

**Flashing from the running phone works and is cheaper than a fastboot cycle.** No
cable-holding, no Volume Up. Stage the image to `/tmp` first and check its md5 there,
so a bad transfer cannot reach the partition, then `dd ... conv=fsync` and read back:

    scp boot-images/boot-r84.img mahan@172.16.42.1:/tmp/
    ssh mahan@172.16.42.1 'md5sum /tmp/boot-r84.img'
    ssh mahan@172.16.42.1 'sudo dd if=/tmp/boot-r84.img of=/dev/disk/by-partlabel/boot bs=4M conv=fsync; sync'
    ssh mahan@172.16.42.1 'sudo head -c 18219008 /dev/disk/by-partlabel/boot | md5sum'

Two things about that md5. It is taken **over the image length, not the partition** -
the partition is 20 MB and hashing all of it includes trailing padding, which is why
a whole-device `md5sum` gives `fa97d700...` and not the documented number. And the
bytes past the new image are left over from whatever was there before; harmless,
since the bootloader reads the length from the header.

**`dd` to boot is enough only when nothing new is a module.** `uname -r` is
`6.16.12` for every one of these builds - `pkgrel` only moves `uname -v` - so they
share `/lib/modules/6.16.12`, and r84 ran happily on r56's modules with `wcn36xx`,
`mac80211` and bluetooth loaded and `wlan0` connected.

**r85 broke that, and the reason is worth knowing.** `SLIM_QCOM_NGD_CTRL` cannot be
built in here: it `depends on QCOM_RPROC_COMMON`, which the remoteproc drivers
`select` while themselves being `=m`, and a `select` from a module caps the selected
symbol at `m`. So setting it `=y` in the config is silently downgraded, and the
driver ships as `slim-qcom-ngd-ctrl.ko`. Since `CONFIG_MODVERSIONS=y` and r85 also
moves the QMI and PDR helpers from `m` to `y`, reusing the old `/lib/modules` was not
safe either. The full path, which is what was done:

    scp linux-...-r85.apk mahan@172.16.42.1:/tmp/
    ssh ... 'sudo apk add --allow-untrusted /tmp/linux-...-r85.apk'   # modules + initramfs
    ssh ... 'cat /boot/initramfs' > initramfs                          # AFTER apk add
    tools/mkbootimg.py --kernel vmlinuz --dtb ...amami.dtb --initramfs initramfs -o boot-r85.img
    # then stage, verify and dd as above

`apk add` regenerates the initramfs and runs `boot-deploy`, which writes
`/boot/boot.img` as a **file** and does not touch the partition - checked, the
partition still held r84 afterwards. Its image is unusable anyway, since it carries
`boot-deploy`'s own `quiet splash plymouth` command line instead of the one this port
needs. See [[xperia-z1c-flashing-modules]].

**Blacklist a new driver for its first boot.** `/etc/modprobe.d/` with
`blacklist slim_qcom_ngd_ctrl` meant the first r85 boot exercised only the DT, and
the driver went in afterwards by hand with dmesg watched - a crash then costs a
`modprobe`, not a boot loop. An explicit `modprobe` ignores the blacklist, which is
what makes this work. Removed once it was known safe.

### The next jobs

1. **The WCD9320 codec driver** - now the only thing between this phone and
   sound, and the largest single piece of audio work. APR, the Q6 services, the
   frontend DAIs and SLIMbus are all up, and the Taiko enumerates on the bus;
   mainline simply has no driver for that part. wcd9335 is the closest relative
   to work from. See Phase 3.
2. **Deep suspend**, now measured to be worth it: s2idle saves only 37%, and the gap
   between 156 mA and single-digit standby is the largest remaining battery item. See
   Phase 2.
3. **Proximity**, still the one sensor that enumerates but never reports.

### Two traps worth not rediscovering

- **`/sys/kernel/debug/regmap/0-01/registers` is unusable on pm8941.** Every register
  is a separate SPMI transaction and the file walks the whole address space, so even
  a `head -c` of the first few hundred KB does not return, and the reader is
  effectively unkillable while it runs. Three attempts pushed load average past 5.
  The SMBB notes elsewhere in this file describe reading `0-00` that way - treat that
  as "for a small range, patiently", not as a general technique.
- **Do not `pkill -f <script>` from the host** to clean up something running on the
  phone. The pattern matches the local `ssh` command that contains the script name,
  so it kills the session issuing it. Kill by PID over ssh, on the phone.

## Where the port stands

Working: panel, touch, Xfce on freedreno, WiFi, Bluetooth, charging (on a real
supply), battery percentage, USB networking, sensors bar proximity, the notification
LED, the vibrator, suspend (s2idle), GPU and CPU frequency scaling, CPU thermal
throttling, and SLIMbus - the Taiko enumerates, though nothing can drive it yet.

Not working: audio (the codec driver is all that is left), deep suspend.

**The sensor story is complete as of 2026-09-16**: accelerometer, gyroscope,
magnetometer, proximity and ambient light all work, each enabled on its own. See
Phase 1.

The vibrator **works** as of `0040` - felt, not merely enumerated - and the ADSP
audio transport is up as of `0039` with all four Q6 services attached as of `0041`.
Audio still makes no sound: the codec driver is the blocker, see below.

The GPU IOMMU works as of `0034`-`0036`. The MDP half (`0037`) reclaims the 192MB
carveout but blanks the panel, and all of it is out of the build.

### Where the build recipe actually is

Worth stating because it lives on disk in pmaports, not in this repo, so nothing here
records it and a new session would have to look:

- **Flashed on the phone: r90**, and the pmaports recipe is also r90, so they
  agree. It is `0001`-`0029` as usual plus `0039` (APR), `0040` (vibrator),
  `0041` (q6asm DAIs), `0042`-`0044` (SLIMbus), `0045`, `0047` and `0048`, with `CONFIG_QCOM_APR`, the
  `SND_SOC_QDSP6_*` symbols and `CONFIG_SLIMBUS` on. No IOMMU patches,
  `# CONFIG_ARM_SMMU is not set`.
- **`uname -v` prints `pkgrel` + 1.** r85 reports `#86`. Easy to misread as having
  booted the wrong build.
- Earlier images are kept in `~/Devices/Xperia-Z1-Compact/boot-images/`: r84
  (`d4550bf58700118ce0b3ee31aee67999`) is the last build before SLIMbus, and
  r56-rebuilt (`69b89a70e0a216cc128579bea40f5561`) reproduces what was flashed for
  most of this port's life.
- Apks r57-r86 in `~/.local/var/pmbootstrap/packages/` are a mix of experiments;
  several are IOMMU builds. Numbering is monotonic but the contents are not a
  progression - check the config inside one before trusting it.

## What is instrumented

These did not exist before and they change which experiments are cheap:

- **An ammeter.** `0023` fixed `qcom-spmi-iadc`; battery current is signed microamps
  at ~0.55 mA resolution, cross-checked between two sense resistors to 5-7%.
  Measuring needs the USB cable **out** - on a host port the battery floats.
- **pstore.** `ramoops` with a 1 MB console buffer. Survives a panic or soft reboot,
  not a forced power-off. `systemd-pstore` moves records to
  `/var/lib/systemd/pstore/`.
- **A panic net** in the standard command line:
  `sysctl.kernel.panic_on_rcu_stall=1 panic=10 rcupdate.rcu_exp_cpu_stall_timeout=21000`.
  Keep all three together; the third is in **milliseconds** and its default fires on a
  harmless expedited stall every boot.
- **A test pattern.** Flash a known-good kernel, `fastboot boot` the experiment, change
  one variable, soak past the known failure point. That found the cpufreq bug.
- **`no_hash_pointers`** on the command line when a `%p` needs to be real. That is what
  turned the IOMMU `-EBUSY` from a guess into a fact.

## Phase 1: read before building

The GPU IOMMU is done - and it was solved by instrumenting the running hardware, not
by finding a source, which is worth remembering. Proximity still needs one.

### The GPU IOMMU: solved, and deliberately not in the build

`0034` and `0035` make the GPU render through its SMMU. Three-minute soak: zero
hangchecks, 55,145 GPU interrupts, fences retiring within three of submission, no
fault on any line.

Two bugs, both found by reading the hardware on a running system rather than by
rebuilding:

- **`SCTLR.AFE` does not work.** `io-pgtable-arm-v7s` sets `AP[0]` - the access flag -
  in every descriptor, and the walk still ends in an access flag fault on the
  ringbuffer. `0035` clears the bit, which also yields the permissions the mappings
  asked for rather than merely silencing the fault.
- **Both SMMU interrupt numbers were wrong**, which is why none of it was ever
  visible. Global fault is SPI 38; the context list is indexed by `CBAR.IRPTNDX`
  rather than by bank number, and the hardware raises on SPI 240 + IRPTNDX, so it has
  to start at 240. Getting this wrong is silent - FSR latches, the transaction is
  terminated, and a faulting GPU looks like an idle one. Getting it off by one is
  worse: the fault lands on a line bound to another bank, whose handler sees a clean
  FSR, and the level-triggered line storms until the kernel says `nobody cared`.

**It stays out of the build**, and now for a measured reason. Like-for-like at
320MHz, `vblank_mode=0`: 780 FPS on the carveout kernel against 154 FPS behind the
SMMU, both with zero hangchecks. Five times the cost, and it reclaims nothing until
the **MDP** has an IOMMU, because `msm_use_mmu()` tests the display controller.

**Where the five-fold cost goes is now measured: translation itself.** Zero SMMU
maintenance calls in five seconds of load, glxgears blocked on the GPU rather than the
CPU (94.5% of a core down to 26.7%), and throughput inversely proportional to pixel
count while a 64x64 window reaches the carveout kernel's own CPU-bound ceiling. No
fixed per-frame cost; a cost on every memory access, i.e. TLB misses walking uncached
page tables.

Ruled out: runtime PM (pinned vs auto is identical to three decimal places), and
`dma-coherent` - `IDR0.CTTW` claims coherent walks are supported, but turning it on
kills the GPU outright and storms both fault lines, because the interconnect is not
coherent with the CPU.

**Page size was the lever, and `0036` took the gap from 5.1x to 1.53x.** IOVAs were
allocated with `PAGE_SIZE` alignment, so `iommu_pgsize()` could never coalesce and
every mapping was a 4KB page. `0036` aligns both the IOVA allocator and the VRAM
carveout allocator to the largest page an object can fill; aligning one without the
other does nothing. Verified in the page tables - 7 sections of 1MB and 92 large pages
of 64KB now, against none before.

| window | carveout | IOMMU, 4KB | IOMMU, `0036` |
|---|---|---|---|
| 200x200 | 855 FPS | 340 FPS | 876 FPS |
| 300x300 | 783 FPS | 154 FPS | 511 FPS |
| 400x400 | 834 FPS | 88 FPS | 276 FPS |

The rest of the gap is the 366 remaining small pages and the cost of translating at
all. Whether to turn the IOMMU on is now a real judgement call rather than an obvious
no - it buys GPU memory protection that the carveout cannot.

Also still untested on its own: `msm8974_smmu_write_s2cr` forces `NSCFG`/`MEMATTR` on
a theory that later proved wrong.

The technique is the reusable part. `CONFIG_STRICT_DEVMEM` is off, so `/dev/mem`
reaches any register block directly - but pin its runtime PM first
(`echo on > /sys/bus/platform/devices/<dev>/power/control`) or the read hangs the
bus on an unclocked block.

Two cautions learned the hard way. A GIC pending scan is only evidence if the line was
*not* already pending beforehand - the first pass at the interrupt numbers accepted
SPI 37 while it had been pending from boot, and it was another device's. And a zero
fault counter proves nothing once the faults are fixed; verify delivery by *injecting*
one. Forcing `SCTLR.AFE` back on for a bank is a reliable fault generator here.

Downstream's device tree is worth having as a cross-check and is one command away:
the LineageOS `boot.img` carries a QCDT container of DTBs, and `mdp_iommu` /
`kgsl_iommu` sit in it with real addresses, SIDs and interrupts. It is not the final
authority - its `kgsl_iommu` lists SPI 241 for all three GPU contexts, which is only
right for whichever one lands on IRPTNDX 1 - but it is what flagged the first
interrupt guess as wrong. Prefer **stock** firmware to LineageOS where it matters:
Lineage descends from Sony's GPL tree but drifts, while stock pairs with the
TrustZone image the phone actually boots. Stock is an FTF of `.sin` containers, so it
needs an extra unpacking step.

For the MDP IOMMU, downstream says: base `fd928000`, contexts at `fd930000`+ (the same
base+0x8000 layout, so the `numpage` quirk carries over), global SPI 73, context
interrupts SPI 47 and 46 - and `qcom,iommu-secure-id = <1>`, which `kgsl_iommu` does
not have. TrustZone owns that one.

### The MDP IOMMU: done, and it is what reclaimed the 192MB

`msm_use_mmu()` tests the display controller, not the GPU, so the carveout survives a
perfectly good GPU IOMMU and only goes away here. `0037` adds `mdp_smmu@fd928000` and
points the MDP at it.

Cheaper than expected on every axis. It is the **same hardware as the GPU's SMMU** -
identical probe, and the `numpage` write-back test reads `0xdeadbee0` at `+0x8000`,
agreeing with stock's `mdp_0` at `0xfd930000` - so `0034`/`0035` carry over with **no
new driver code**. Stock and LineageOS describe both IOMMUs identically. And despite
`qcom,iommu-secure-id = <1>`, **TrustZone does not block the non-secure side**, so the
`qcom_scm_restore_sec_cfg` that `arm-smmu-qcom` lacks is not needed.

Result: carveout gone, display fine, `FD330` still the renderer, zero faults on all
six lines the two SMMUs register, and `CmaFree` from 65152 kB to 261760 kB - exactly
192MiB back. Net usable memory gains less, since the buffers now come from ordinary
memory instead of a reservation.

**Boot with `arm-smmu.disable_bypass=0`.** This SMMU sits in the display path whether
or not anything attaches to it, `arm_smmu_device_reset()` rewrites every S2CR before
`impl->reset` runs, and undescribed MDSS masters still have to get through. With the
bypass disabled it blanks the panel just by probing.

**It costs the page-size win.** Without a carveout, GEM comes from shmem as scattered
order-0 pages, so `iommu_pgsize()` cannot coalesce whatever the IOVA alignment is -
walking both SMMUs afterwards finds no sections and no large pages at all. Throughput
returns to the 4KB figures, 329 FPS at 200x200 against 876. Huge pages would fix it
and are not reachable: `HAVE_ARCH_TRANSPARENT_HUGEPAGE` is selected only `if
ARM_LPAE`, which is off - which is also why the IOMMU uses v7s short descriptors.
Having both would need a CMA-backed GEM allocator rather than shmem.

**`0037` is not finished: the panel is black.** The SMMU attaches, the carveout goes
away and about 172MB comes back, but nothing reaches the screen. It was briefly turned
on by default on the strength of console checks - `fb0` registered, backlight lit,
`FD330`, 151 FPS, zero faults - none of which test scanout. The one line `0037`
removes is `no IOMMU, fallback to phys contig buffers for scanout`.

**Measured: the fault is on the page-table walk.** With the bypass enabled so anything
unmatched faults loudly, `cb1 FSR 0x10` (external fault) with `FSYNR0 0x581` - bit 10
is PTWF, `PLVL` 1. The SMMU aborts fetching its own level-1 descriptor. `sGFSR` stays
0, so nothing is unmatched.

The display is not failing to read its framebuffer; **the SMMU cannot read its own
page tables**. Walking them from the CPU works fine, which is what made the first four
attempts chase the wrong transaction.

Dead ends, all tested on hardware: an unmapped MDSS stream (`sGFSR` is 0);
`qcom_scm_restore_sec_cfg` (collapses the stream ID mask to 0 from `cfg_probe`, and
wedges the phone with mmc timeouts and an RCU stall from `init_context` - Sony's TZ is
on the legacy SCM convention and does not mean what `qcom_iommu.c` expects); and
downstream's 18 BFB registers, applied verbatim and read back correctly, with the
fault unchanged.

**The question to answer next:** why can this SMMU's table-walk master not read normal
memory when the GPU's identical SMMU can? Same IP, tables in the same low physical
range. What differs is the clocks, the power domain and the NoC path - so start there,
and compare against how downstream sets up MDSS bus votes before first use.

**Rule for this one: no claim about the display until someone has looked at the
panel.** `fb0`, `bl_power`, `glxinfo` and a frame counter all pass while the screen is
black.

### Proximity: SOLVED 2026-09-16. It needs a second sensor subscribed

**The sensor works.** With the accelerometer subscribed at the same time and a
hand moving over the phone:

    [ 0.0s] values=(0,     56, 0)     far,  raw IR 56
    [15.0s] values=(65536, 525, 0)    NEAR, raw IR 525
    [22.1s] values=(0,    288, 0)     far
    [23.1s] values=(65536, 521, 0)    NEAR
    [26.5s] values=(0,    306, 0)     far
    [29.9s] values=(65536, 518, 0)    NEAR

`values[0]` toggles 0 <-> 65536 - Q16 for 0.0 and 1.0, far and near - and
`values[1]` is the raw IR count. The hardware, the ADSP path, the IIO driver and
its scaling were never broken.

**The whole bug is that proximity emits nothing unless another SMGR sensor is
subscribed at the same time.** Demonstrated three ways, each with a control in the
same run:

| | proximity samples |
|---|---|
| proximity alone | **none, ever** |
| accelerometer running, proximity added | 1 on enable, then one per change |
| accelerometer subscribed then *deleted*, then proximity | 1 on enable |

and through the kernel exactly the same way - `buffer/data_available` stays 0 for
proximity alone, and reads 1 the moment the accelerometer's buffer is enabled
first. Nothing else matters: sampling rate 1 to 100, `val1`/`val2`, primary versus
secondary data type, and `report_rate` across seven values from 0 to
`rate * 32768 * 2` all change nothing on their own.

**Why nobody hit this on Android:** the accelerometer is effectively always
subscribed there, for screen rotation alone, so proximity always had a co-active
sensor. Stock's own `dumpsys` shows only two proximity events in a session, both
`0.00`, which is what an on-change sensor looks like when nothing approaches it -
so that capture never contradicted this either.

**`0047` implements the fix, and it works - verified end to end.** When a PROX_LIGHT
sensor is enabled, the driver now takes out a second subscription on the same
chip's ambient light channel at 1 Hz under report ID `0xfe`, waits 100 ms, and
only then subscribes proximity. With it, **proximity enabled entirely on its own
reaches `buffer/data_available = 1`**, where it was 0 in every previous
measurement. That part is solid and reproducible.

Three things were measured to get there, each with a control:

- **Any partner works, and 1 Hz is enough.** Accelerometer at 50 Hz and at 1 Hz,
  gyroscope at 1 Hz, magnetometer at 1 Hz and this chip's own light channel at
  1 Hz all produce the on-enable report; no partner produces nothing, twice.
  Light is used because it powers no other part - 175uA, and the chip is already
  on.
- **It must be a separate request.** Putting both data types in one request's
  `items[]` subscribes ambient light and leaves proximity silent, which is why
  `0031` is not this fix.
- **The partner has to settle first.** Sending both requests back to back fails
  even though the first QMI transaction has completed; 50 ms was the shortest gap
  measured to work, 0 ms the longest to fail, hence 100 ms.

**Verified end to end 2026-09-16.** Proximity enabled on its own, with the
keepalive as its only company, tracks a hand exactly as it should:

    proximity alone: 14 samples
       [  0] raw=65536  NEAR
       [  1] raw=0      far
       ...alternating, 7 NEAR and 7 far, no spurious readings

and with the ambient light device enabled alongside as an independent witness,
the same run shows light dropping 11.0 -> 0.0 lux while proximity reports 5 NEAR
and 5 far. The witness matters: it is the only way to know a hand was actually
over the sensor, and two earlier attempts at this test failed on exactly that -
they recorded nothing because nobody was at the phone, which is indistinguishable
from a driver that does not work if you are not watching the light.

So `0047` is sufficient on its own. Nothing else has to be enabled for proximity
to work.

**How to test this, because the obvious way misleads.** Never judge proximity by
whether samples arrive, on its own. Enable `qcom-smgr-light` alongside it and
watch the lux: covering the sensor drops it to 0, which is independent proof a
hand was there. Without that witness, "no samples" and "nobody touched the phone"
look identical - and did, twice.

### Ambient light: works, as its own IIO device

`0048` exposes the APDS-9930's ambient light channel as `qcom-smgr-light`, a
second IIO device on the same sensor. Enabled on its own it gives **121 samples
in 6 s at 15 Hz**, reading 11-14 lux in a dim room, which matches what the same
channel reports at the QMI level.

It has to be a second *device*, not a second channel, because the DSP will not
report both of a sensor's data types from one subscription - the same constraint
that rules out `0031` as a proximity fix. So a sensor's secondary data type gets
its own subscription, and needs a report ID distinct from the primary's: the top
bit marks it, since sensor IDs are all well under `0x80`. The report handler
routes `sensor->id` to the primary IIO device and `sensor->id | 0x80` to the
secondary one.

No scaling work was needed - the driver's generic branch already gives
`1/65536`, and light is reported as lux in Q16.

Ambient light needs no keepalive of its own: unlike proximity it reports happily
on its own, and is itself a perfectly good second subscription.

**One loose end:** light samples carry a timestamp of 0, where proximity's are
populated. Harmless for reading values, wrong for anything that cares about when
they were taken.

**How this stayed hidden for so long, which is the transferable part.** Every
earlier measurement enabled proximity on its own, so every one of them was
measuring a case that cannot work. The first IIO read that ever returned 16 bytes
was dismissed here as stale buffer content - it was real, and it worked because
that test enabled the accelerometer first and proximity second. Tidying that
script into a "clean" one that tested proximity in isolation removed the only
reason it had worked.

## Phase 2: deep suspend

**The biggest remaining lever on this phone**, bigger than the IOMMU, and as of
2026-09-14 that is measured rather than asserted. It is why idle costs ~248 mA and
why suspending saves only 37% of it: cores collapse individually while the SoC never
does, so the RPM stays up, rails stay put and DDR stays refreshed.

It is unimplemented, not unconfigured, and that is now verified three ways rather
than assumed. `arch/arm/mach-qcom` holds only `Kconfig`, `Makefile` and `platsmp.c`;
nothing anywhere registers `platform_suspend_ops`; and the phone itself reports

    /sys/power/state:     freeze mem
    /sys/power/mem_sleep: [s2idle]

with no `deep` offered, so `mem` is just s2idle under another name. `ARM_PSCI` is off,
so there is no firmware route either.

**Per-core idle is already at mainline's maximum**, which is worth knowing before
looking for easy wins there. `cpuidle-qcom-spm.c` offers exactly one state type,
`qcom,idle-state-spc` - standalone power collapse - and no system-wide variant, and
the phone uses it well: 74799 entries and 1740 seconds of residency in a short uptime,
against 25640 in plain WFI. The cores collapse. The SoC does not.

Three separate pieces are missing, each verified in tree:

1. **No platform suspend ops.** Nothing implements `PM_SUSPEND_MEM`, so there is
   nothing for `mem_sleep` to select.
2. **No system-wide SPM programming.** `cpuidle-qcom-spm.c` knows only standalone
   collapse. It does already call `qcom_scm_set_warm_boot_addr(cpu_resume_arm)`, so
   the resume path exists and is proven - that part would not have to be invented.
3. **No RPM sleep-set votes.** `QCOM_SMD_RPM_SLEEP_STATE` is defined in
   `include/linux/soc/qcom/smd-rpm.h`, and `qcom_smd-regulator.c` never uses it -
   zero occurrences. Mainline votes only the active set, so even a collapsed SoC would
   leave the rails where they are. This is the piece that actually saves the power,
   and it is independent of the other two.

That last point suggests the cheapest first experiment by a wide margin: sleep-set
votes are a regulator concern, not a suspend concern, and could be investigated on
their own without implementing suspend at all.

**Measured 2026-09-14, and the answer is that this is worth doing.**

| state | current | real runtime |
|---|---|---|
| suspended (s2idle) | **156 mA** | 11.2 h |
| idle, screen off | 248 mA | 7.1 h |
| idle, screen on | 400 mA | 4.4 h |

s2idle removes only **37%** of the draw, because the cores collapse and the SoC does
not. 156 mA of standby is dire for this class of phone - a real suspend should be
single-digit milliamps - and the gap between those two numbers is the whole prize:
roughly 11 hours of standby against several days.

**And the pack is at about 56% health,** ~1750 mAh against 3140 nameplate. Phase A of
that run consumed a measured 166.2 mAh while the OCV curve said 9.48% of the pack had
gone. Every runtime figure recorded before this was optimistic by ~1.8x; the currents
were right, the divisor was not. Worth knowing before attributing any future
improvement to software.

Method matters here and is written up in [[xperia-z1c-battery-baseline]] - in short,
`capacity` is OCV-derived from instantaneous voltage so it tracks *load* rather than
charge, every endpoint has to be read at a matched load, and the conversion needs
Sony's OCV table because voltage is not linear in charge over this range. The raw
data and the derivation are in `docs/measurements/s2idle-2026-09-14/`, and the
script that produced them is `tools/s2idle-test.sh`, so the run can be repeated
against any future suspend work rather than re-invented.

## Phase 3: audio

Surveyed properly, and the shape of the work is now known rather than guessed.

**The hardware**, from stock's device tree: the codec is `taiko_codec`,
`compatible = "qcom,taiko-slim-pgd"` - a **WCD9320 (Taiko) on SLIMbus**. The bus is
`slim@fe12f000`, `qcom,slim-ngd`, reg `0xfe12f000` (0x35000) and `0xfe104000`
(0x20000). The card is `qcom,msm8974-audio-taiko`, with the usual pile of
`qcom,msm-dai-q6-sb-*` SLIMbus DAIs and a quaternary MI2S.

**What mainline has:** APR over SMD (`qcom,apr-v2`), the full Q6 stack
(`q6core`/`q6afe`/`q6asm`/`q6adm`/`q6routing`), the SLIMbus core, an NGD controller
(`qcom,slim-ngd-v1.5.0` for 8996, `-v2.1.0` for SDM845) and a non-NGD one for
apq8064.

**What mainline does not have: a WCD9320 driver.** The codecs present are wcd9335,
wcd934x, wcd937x/938x/939x - all later parts. That is the blocker, and it is a large
one; nothing downstream of it can make sound without it.

So the work splits into three milestones, and only the first two are small:

1. **APR and the Q6 services - done, booted and working.** `0039` adds the `apr` node
   under the ADSP's existing `smd-edge`, the same edge `qcom_smgr` already uses for
   sensors, with `q6core`, `q6afe`, `q6asm` and `q6adm`. Needs `CONFIG_QCOM_APR` and
   the `SND_SOC_QDSP6_*` symbols. Booted as r83:

        remoteproc remoteproc2: remote processor adsp is now up
        qcom,apr ...: Adding APR/GPR dev: aprsvc:service:4:3    (q6core)
        qcom,apr ...: Adding APR/GPR dev: aprsvc:service:4:4    (q6afe)
        qcom,apr ...: Adding APR/GPR dev: aprsvc:service:4:7    (q6asm)
        qcom,apr ...: Adding APR/GPR dev: aprsvc:service:4:8    (q6adm)

   The transport to the DSP works. No sound card appears, which is expected with no
   codec driver.

   **One thing was left over from it:**

        q6asm-dai ...:dais: No dais found in DT
        q6asm-dai ...:dais: probe with driver q6asm-dai failed with error -22

   `0039` declares the `dais` containers but not their children, and `q6asm-dai`
   counts them with `of_get_child_count()` and returns `-EINVAL` on zero. On the
   boards that work, the `dai@N` nodes live in the *board* DTS rather than the SoC
   dtsi - `msm8916-modem-qdsp6.dtsi` is the closest-in-era example - because they
   describe how many streams the board wants, not anything the SoC fixes.

   **`0041` adds them to amami's `.dts`,** four frontend DAIs matching msm8916's set:
   MULTIMEDIA1 playback, MULTIMEDIA2 capture, MULTIMEDIA3 playback, MULTIMEDIA4
   compressed. `reg` is a session id and `q6asm.h` caps `MAX_SESSIONS` at 8, so they
   have to stay inside MULTIMEDIA1..8 - the driver skips any child outside that
   without saying so.

   Only `q6asm` needs this. `q6afe-dai` builds its DAI list from
   `q6dsp_audio_ports_set_config()` rather than from DT children, so it probes fine
   with an empty container, and `q6core`/`q6adm` have no DAIs at all.

   **SOLVED 2026-09-15, booted as r84 and verified on the device.** `q6asm-dai` is
   bound - the symlink exists under `/sys/bus/platform/drivers/q6asm-dai/` - and
   `/sys/kernel/debug/asoc/dais` lists `MultiMedia1`..`MultiMedia4`, the four this
   patch declares, alongside q6afe's backend DAIs (`SLIMBUS_*`, `HDMI`, `USB_RX`).
   The `No dais found in DT` failure is gone.

   Check the binding and the DAI list rather than the absence of the error message:
   a driver that never probed at all also logs nothing.
2. **SLIMbus - SOLVED 2026-09-15. The Taiko enumerates.** `0042`-`0044`, in the
   build as r85 and flashed.

        SLIM SAT: Rcvd master capability
        SLIM controller Registered
        /sys/bus/slimbus/devices/217:a0:0:0     the interface device
        /sys/bus/slimbus/devices/217:a0:1:0     the PGD

   The controller was the easy half. Both NGD compatibles mainline already had
   point at the *same* `ngd_v1_5_offset_info`, so the version in the name carries
   no register differences at all and `qcom,slim-ngd-v1.4.0` is simply a third
   entry against the same data (`0042`). `0043` adds the bus and its BAM to the
   SoC dtsi, every address and interrupt taken from stock's own `slim@fe12f000`:
   `0xfe12f000 0x35000` and `0xfe104000 0x20000`, SPI 163 and 164. The ADSP owns
   the bus and the AP is a satellite on it, so the BAM is `qcom,controlled-remotely`
   on execution environment 1 of 2, as on 8996.

   `0044` declares the Taiko. Both enumeration addresses come from stock's
   `taiko_codec`, which stores them as the raw 6-byte `struct slim_eaddr` -
   `__packed`, little-endian, `{ instance, dev_index, prod_code, manf_id }`:

        elemental-addr                   = 00 01 a0 00 17 02   the PGD
        qcom,cdc-slim-ifd-elemental-addr = 00 00 a0 00 17 02   the interface dev

   so both are manufacturer `0x217` product `0xa0`, differing only in device
   index, which mainline spells `compatible = "slim217,a0"` with `reg = <1 0>`
   and `<0 0>`. The two device names that appear are those values read back.

   **Nothing binds to them, and that is expected** - mainline has wcd9335 and
   later, not the WCD9320. Milestone 3 is the codec driver.

   **A wrong turn worth keeping, because it nearly became a fact.** The first
   attempt concluded "the ADSP advertises no QMI services" and it was written up
   that way. It was an artefact of `tools/qrtr-services.py` guessing the QRTR
   command numbers: `NEW_SERVER` and `NEW_LOOKUP` are **4** and **10** in
   `include/uapi/linux/qrtr.h`, not 2 and 7, so the probe sent `HELLO` and
   `RESUME_TX` and heard nothing back. The script now publishes a fake service and
   checks its own lookup finds it before reporting, which is what caught it - and
   with the right constants the phone reports 36 services with `0x301` among them.
   There is no known-good QMI service here to check a probe against, since wcn36xx
   uses `WCNSS_CTRL` over SMD, so a probe that cannot test itself is worth nothing.

   **Reload the driver by rebooting, not `rmmod`.** `of_qcom_slim_ngd_register()`
   leaves its `qcom,slim-ngd.1` platform device behind on remove, so a second
   `modprobe` dies on `kobject_add_internal failed ... -EEXIST` and the controller
   never probes again. Looks like a SLIMbus failure and is not one.

3. **The WCD9320 driver - it already exists, and it compiles.** `0049`.

   **Do not write this from scratch.** `msm8974-mainline/linux` carries a Taiko
   driver on branch `old-4.18.0/qcom-audio-wip`: `wcd9320.c`, `wcd9320.h`,
   `wcd9320-registers.h`, `wcd9320-regmap.c`, `wcd9320-slim.c`, plus `wcd-clsh.c`
   and `wcd-slim.h`. 8252 lines, and checking for it took one API call against
   several sessions of writing.

   **It forward-ports to 6.16 in nine small changes**, which is the surprise - it
   was written after the `snd_soc_codec` to `snd_soc_component` conversion, so the
   one genuinely painful ASoC migration was already done. What it needed:

   - `#include <linux/of_platform.h>` for `of_platform_populate()`
   - `snd_soc_component_read32()` -> `snd_soc_component_read()`, 21 sites, same
     signature and return semantics
   - the `WCD9335_IS_1_1`/`IS_2_0` macros, which `wcd-clsh.c` reaches for because
     it is shared with the WCD9335 in its home tree. Carried in `wcd-clsh.h`
     rather than pulling in a wcd9335 header. **Both are dead code here**: the
     WCD9320 never assigns `codec_version` - the assignment is commented out
     upstream - so it stays 0, `WCD9335_VERSION_1_0`, and neither macro matches.
   - `slim_stream_config` lost its `prot` field; the assignment is dropped
   - `slim_stream_allocate()` takes a name now, and the config goes to
     `slim_stream_prepare()`
   - `set_channel_map`/`get_channel_map` gained `const` qualifiers, propagated
     into `mywcd_slim_init_slimslave()`
   - `platform_driver::remove` returns void
   - a missing `return ret` in `mywcd_slim_init_slimslave()`
   - the two halves each had a module entry point, which does not link when they
     are one module. The SLIMbus half now owns `module_init`/`module_exit` and
     registers the platform driver too, which matches the order things have to
     happen in anyway: the slim probe is what calls `of_platform_populate()` to
     create the device the codec driver binds to.
   - `MODULE_DEVICE_TABLE(slim, ...)` was missing, so it could never autoload

   **Its device ID table is `{0x217, 0xa0, 0x1, 0x0}` and `{0x217, 0xa0, 0x0, 0x0}`
   - exactly the two addresses already enumerating on this phone's bus**, and the
   built module carries `alias: slim:217:a0:*`. It is aimed at this hardware.

   **Built as r88 and deliberately NOT flashed.** The module autoloads on that
   alias, and there is no DT node for it yet, so probing it on the phone is a
   fresh-session job rather than a 3am one.

   **`0050` wires it into amami's DT**, every value read out of stock with
   `tools/romdtb.py`: reset on msmgpio 63, the interrupt on msmgpio 72 (stock's
   `wcd9xxx-irq`, named `cdc-int`), the MCLK gate on PM8941 GPIO 15, and
   `qcom,cdc-mclk-clk-rate` `0x927c00` - 9.6MHz, which is CXO/2, so
   `RPM_SMD_DIV_CLK1`. Stock's phandles put the buck rail on S2, tx-h/rx-h/px-1
   on S3 and the three 1.2V rails on L1; the driver asks for them under its own
   names (`vdd-buck`, `vdd-tx-h` ...), so the mapping is by phandle, not by name.

   **It also needs `ifd = <&taiko_ifd>;`.** `wcd9320_slim_probe()` looks the
   interface device up by that phandle, and without it the PGD half stops at
   `No Interface device found` - which is exactly what the first attempt did.

   **`0051`** adds `qcom,msm8974-sndcard` to `sound/soc/qcom/apq8096.c`. That
   driver is 145 lines and entirely generic - `qcom_snd_parse_of()` builds the
   card from the DT dai-links - and its one SoC-specific constant, a 9.6MHz codec
   MCLK, is the rate the Taiko wants too.

   **How far it gets, as of 2026-09-16.** The codec probes and talks to the
   hardware:

        gonna write
        ragmap ret: 0            <- a register write over SLIMbus succeeded
        WCDPROBESTART
        WCD PROBE!! YAY
        WCD OSC Freq: 70
        WCD dai 0 .. WCD dai 9   <- ten DAIs registered

   and `/sys/kernel/debug/asoc/components` lists the codec beside q6routing and
   the q6asm/q6afe DAI sets.

   **`0052` fixes the oops, and there is now a sound card.** See below; what
   follows is how the crash was found, kept because the method transfers.

   **The oops it used to hit:**

        Unable to handle kernel NULL pointer dereference at virtual address 0
        PC is at dapm_connect_mux+0x2c/0xec
        LR is at snd_soc_dapm_add_path+0x184/0x3f4

   `dapm_connect_mux()` starts with `&w->kcontrol_news[0]` and immediately reads
   `e->reg` through it, so a sink widget with a NULL `kcontrol_news` faults there.
   None of the nine `SND_SOC_DAPM_MUX` widgets in `wcd9320.c` is declared with a
   NULL control, so the likely cause is a route whose sink resolves to a widget
   that is not a mux - plausibly one crossing into q6routing's DAPM rather than
   the codec's own. **That is the next thing to chase**, and printing the route
   being added when it faults is the cheap way in.

   **How it was found, without rebuilding the kernel.** `CONFIG_SND_SOC=y`, so
   adding a printk to the core would have cost a flash cycle per guess. Instead
   `CONFIG_KPROBE_EVENTS=y` is on - mount `tracefs` and ask the running kernel:

        mount -t tracefs nodev /sys/kernel/tracing
        echo 'p:dcm dapm_connect_mux ctrl=+0(%r2):string wname=+0(+4(%r3)):string' \
            > /sys/kernel/tracing/kprobe_events
        echo 1 > /sys/kernel/tracing/events/kprobes/dcm/enable

   `$arg1`-style arguments do **not** work on arm32 - it needs the
   `HAVE_FUNCTION_ARG_ACCESS_API` the architecture lacks - so use the registers:
   `%r2` is `dapm_connect_mux()`'s third argument and `%r3` its fourth, and
   `+4(%r3)` is `snd_soc_dapm_widget::name`, `id` being the u32 in front of it.
   Three lines came out, and the last was the fault:

        ctrl="AIF1_PB" wname="SLIM RX1 MUX"   <- fine
        ctrl="AIF1_PB" wname="SLIM RX2 MUX"   <- faulted

   **The bug.** `slim_rx_mux[]` is declared `[WCD9320_RX_MAX]`, thirteen entries,
   and filled with **two**, from index 0. The widgets index it by `WCD9320_RX1`
   through `RX7` - one through seven - so `SLIM RX1 MUX` got the valid entry at
   index 1 and `SLIM RX2 MUX` got zeroed memory at index 2. `dapm_connect_mux()`
   casts that entry's `private_value` to a `struct soc_enum` and reads `e->reg`
   off it immediately, which is the NULL dereference at address 0.

   A second bug sat underneath: index 1 holds the control *named* "SLIM RX2 Mux",
   so even the working widget had the wrong control - the array was off by one
   against the enum it is indexed by. `0052` fixes both with designated
   initializers for `RX1`..`RX7`.

   **What works now.** Loading the fixed codec gives a card:

        0 [Compact        ]: apq8096 - Xperia Z1 Compact
        /dev/snd/pcmC0D0p

   and `speaker-test -D hw:0,0` runs the whole chain - the DSP takes the stream,
   SLIMbus channels are prepared and enabled, MCLK and the master bias come up,
   and the codec's RX path activates:

        wcd9320_set_interpolator_rate: AIF_PB DAI(0) connected to RX2, 48000
        wcd_slim_stream_prepare / wcd_slim_stream_enable
        wcd9320_codec_enable_mclk -> enable_master_bias -> enable_mclk
        wcd9320_codec_enable_rx_bias / wcd9320_codec_enable_slimrx

   **It is silent, and the reason is known.** Tested with headphones in the jack
   and the routing set by hand: the stream runs to completion and nothing is
   heard. The log says why:

        qcom,slim-ngd: Tx:MT:0x0, MC:0x60, LA:0x0 failed:-110
        ASoC error (-5) at snd_soc_component_update_bits() ... register [0x00000b56]

   `0xb56` is in the **interface device's** register space - the SLIMbus port
   configuration - and those writes are going to **logical address 0**, because
   the interface device never gets one:

        wcd9320-slim 217:a0:0:0: Failed to get logical address

   So the ports are never configured, no audio data crosses the bus, and the
   stream plays into nothing. The PGD is fine - its regmap write returns 0 at
   probe - which is why everything upstream reports success.

   **`0053` fixes the addressing, and the timeouts are gone.** The interface
   device does not answer on the bus until the codec's digital core is running,
   and `wcd9320_bring_up()` is what starts it (`A_CDC_CTL` 0 then 3). Asking for
   its logical address *after* bring-up succeeds; the
   `Tx:MT:0x0, MC:0x60, LA:0x0 failed:-110` timeouts disappear. Not fatal if it
   fails, as `wcd9335` also ignores the result.

   **Asking before bring-up makes it worse**, which is what the first attempt did:
   both devices then fail to get an address and no card appears at all,
   reproducibly across a module reload. Order is the whole point.

   **What is still silent, and why - `wcd-clsh.c` is for the wrong codec.**
   Register `0xb56` still fails, now as a plain `-EIO` rather than a timeout, and
   it is not an interface-device register at all:

        wcd-clsh.c:10: #define WCD9XXX_A_CDC_RX1_RX_PATH_CFG0  (0xB56)

   **All twenty** register addresses in `wcd-clsh.c` are `>= 0x400`, and the
   WCD9320's whole map ends at `WCD9320_NUM_REGISTERS` = `0x400`. They are
   WCD9335 addresses: that file is shared between the two codecs in its home tree
   and was only ever correct for the WCD9335. Every Class-H write a Taiko makes
   through it is out of range and rejected, so the Class-H block and the
   headphone output path are never configured - which is exactly why the stream
   runs and nothing is heard.

   The Taiko has its own Class-H block - 36 `WCD9320_A_CDC_CLSH_*` registers from
   `0x320` - and its own headphone registers at `0x1AE`/`0x1B1`. `0054` stubs
   `wcd_clsh_fsm()` out rather than writing at random; Class-H is a power
   optimisation, not a prerequisite for sound.

   **Class-H was not the only thing, and nor was the addressing.** With `0053`,
   `0054` and `0055` in, **every codec register write succeeds, no SLIMbus
   transaction fails, and it is still completely silent.**

   `0055` is a real bug worth knowing about: `wcd9320_ifd_regmap_config` had **no
   `max_register`**, which regmap defaults to 0 - so the interface device's map
   permitted exactly register 0 and silently rejected every port write (the
   enables at `0x30`, the config bytes, the channel registers at
   `0x100 + 4*port`). Its debugfs dump was one line. It now covers 1024.

   **What the hardware says.** Read back while a tone plays, the whole path is up:

        DAPM: SLIM RX1, RX1 MIX1, RX1 INTERP, CLASS_H_DSM MUX, HPHL DAC, HPHL - all On
        0x1ab = 0xb0   HPHL PA enable bit (0x20) set
        0x1b1 = 0xc0   HPHL DAC enable bit (0x80) set

   So the analog output stage is enabled and the digital path is powered. Nothing
   is failing. There is simply no audio arriving.

   **The prime suspect: the SLIMbus channel setup is `#if 0`-ed out.**

        wcd9320.c:2430  #if 0  wcd_slim_alloc_slim_sh_ch(..., SLIM_SINK)   RX channels
        wcd9320.c:2454  #if 0  wcd_slim_alloc_slim_sh_ch(..., SLIM_SRC)    TX channels
        wcd9320.c:2583  #if 0  the RX port config loop, channel regs + watermark

   This driver is a work in progress and that is the part left unfinished, which
   fits every observation: everything powers up, nothing errors, no data moves.

   **Those `#if 0` blocks are superseded, not missing - checked, so do not chase
   them.** The driver uses the modern `slim_stream_prepare()`/`enable()` API
   instead, and the channels really are configured. The codec reports them to the
   machine driver on every playback:

        wcd9320_get_channel_map: slot_num 0 ch->ch_num 145
        wcd9320_get_channel_map: slot_num 1 ch->ch_num 146

   With `BASE_CH_NUM` 128 those are slave ports 17 and 18, inside Taiko's RX range
   (ports 16-28, 13 of them). The register bases match downstream exactly -
   `0x180 - 16*4` and `0x040 - 16`, where downstream's
   `TAIKO_SB_PGD_OFFSET_OF_RX_SLAVE_DEV_PORTS` is also 16 - and the DSP side is
   right too: `SLIMBUS_0_RX` is 2, so `q6slim_set_channel_map()` takes its RX
   branch and stores `ch_mapping = {145, 146}`. Both ends agree.

   ### What is actually unfinished: the codec's interrupt layer

   A full playback log ends with:

        wcd9320_codec_enable_slim_chmask: Slim close tx/rx wait timeout, ch_mask:0x60000

   `0x60000` is bits 17 and 18 - precisely those two ports. `ch_mask` bits are set
   when the ports open and are meant to be cleared by the codec's SLIMbus port
   interrupt handler, which then wakes `dai_wait`. They are never cleared, and
   `/proc/interrupts` says why:

        106:  0  0  0  0  msmgpio  72  Level  wcd

   **Zero interrupts, ever.** The DT wiring is right and
   `devm_request_threaded_irq()` does run, but inside the codec:

   - `wcd9320_slimbus_irq()` is **defined and never referenced** - line 3110 is its
     only occurrence in the file. The handler that clears `ch_mask` is never
     registered.
   - `wcd->irq_data = control->irq_data;` is **commented out**, so no
     `regmap_irq_chip` is ever set up for the codec's internal interrupt
     controller and `wcd9320_request_irq()` could not work even if it were called.

   So the interrupt support simply is not implemented. That is a real piece of
   work: a `regmap_irq_chip` over the codec's `A_INTR_*` registers, then hooking
   `wcd9320_slimbus_irq` to `WCD9320_IRQ_SLIMBUS`.

   **`0056` fixes the init sequence but does not fix the interrupt.** It replaces
   the ad-hoc writes `wcd9320_bring_up()` used to end with - which masked most
   sources again - with the sequence `wcd9xxx-irq.c` uses downstream: everything
   edge triggered except SLIMBUS, which is level high, so `INTR_LEVEL0` bit 0
   set; masks are 1-to-mask, so `0xfe` on register 0 and `0xff` elsewhere; and
   `INTR_MODE` `0x02`. Worth keeping because the old writes were provably wrong,
   but the interrupt still never fires.

   **And the reason why is the next clue: some of those writes do not stick.**
   Read back afterwards:

        09c: ff   INTR_CLEAR0 - our write landed
        094: 00   INTR_MASK0  - we wrote 0xfe
        0a0: 00   INTR_LEVEL0 - we wrote 0x01

   `CLEAR0` holds, `MASK0` and `LEVEL0` do not. The likely explanation is that
   something re-initialises the cache after `wcd9320_bring_up()` runs - the codec
   platform driver probes later, and `wcd9320_regmap_config` has
   `REGCACHE_RBTREE` with a `wcd9320_defaults` table, so a `regcache_sync()` would
   write the POR values back over them. **Check that before writing an irq chip**:
   an irq chip programming the same registers would be undone the same way.

   **`0058` fixes a real bug in the handler**: it read and acknowledged only
   `INTR_STATUS0..2`, three of four registers. Anything latched in `STATUS3`
   could never be cleared, which on a level-triggered line means the codec holds
   the interrupt asserted forever. It also fixes `1 << i & 7`, which parses as
   `(1 << i) & 7` where `1 << (i & 7)` was meant.

   ### The interrupt line: what is actually known

   The pin is fine. `/sys/kernel/debug/gpio` shows:

        gpio72: in low func0 2mA pull up

   muxed to GPIO (`func0`), an input, pulled up - and sitting **low**. A pull-up
   holding low looks exactly like an asserted open-drain active-low interrupt,
   so requesting `IRQF_TRIGGER_LOW` instead of downstream's `IRQF_TRIGGER_HIGH`
   was tried. **It fires - and it is spurious.** Thousands of interrupts, and the
   handler reads every status register as zero:

        irq 106 0 0 0 0

   So the low level is not the codec reporting anything. That change is reverted;
   it bought an interrupt storm and no information. `IRQF_TRIGGER_HIGH` stands.

   **Which leaves two candidates, and they are testable.**

   1. **msmgpio 72 may not be the codec's interrupt on amami.** It came from
      stock's `wcd9xxx-irq` node (`interrupts = <0x48 0x0>`, named `cdc-int`), but
      that was read out of the stock tree rather than confirmed against this
      board. A line that idles low under a pull-up is odd for an unused input.
   2. **The codec's `0x090`-`0x0A2` block may not be reachable at all.** Writes to
      `INTR_MASK0` (`0xfe`) and `INTR_LEVEL0` (`0x01`) do not stick - both read
      back `0x00` - and all four `INTR_STATUS` registers read `0x00`, while
      `0x1ab` and `0x1b1` in the analog block read sensible values (`0xb0`,
      `0xc0`). Everything below `0x100` is marked volatile, "top level registers
      which can be written by the Taiko core driver", which hints they are
      reached differently downstream. If that block is unreachable the codec can
      never raise an interrupt, and no amount of polarity work will help.

   Settling (2) first is cheaper: pick any register under `0x100` with a known
   non-zero POR value and see whether it reads back correctly.

   **Whether that alone restores audio is not proven.** The SLIMbus data path is
   hardware and interrupts are status reporting, so it is possible sound needs
   something further. But it is the one concrete unimplemented subsystem left on
   the path, and the close timeout is direct evidence it matters.

   **Use the downstream tree for it.** The driver itself cites
   `LineageOS/android_kernel_sony_msm8974`; `drivers/mfd/wcd9xxx-irq.c` there is
   the reference for the interrupt controller and `wcd9xxx-slimslave.c` for the
   port setup - which has already been checked and matches.

   **An earlier wrong turn, kept because it is the same trap:** `wcd9335` calls
   `slim_get_logical_addr(wcd->slim_ifc_dev)` in its `device_status` callback and
   ignores the result; `wcd9320` never calls it at all, and it *does* have a
   `device_status` callback in the same shape. Adding the call there makes things
   **worse**: both devices then fail to get an address and no card appears at all,
   reproducibly, across a module reload. That attempt is reverted and not kept as
   a patch - the useful part is this paragraph. Whatever the core needs before it
   can hand out an address for `217:a0:0:0`, an extra request at that point is not
   it.

   **So the next question is why the SLIMbus core cannot assign a logical address
   to the interface device**, when it manages one for the PGD on the same bus.
   That is the single thing between here and audible sound.

   **The routing has to be set by hand** in any case; nothing sets it up
   automatically, and without it MultiMedia1 reports "no backend DAIs enabled":

        amixer -c 0 cset name='SLIMBUS_0_RX Audio Mixer MultiMedia1' 1
        amixer -c 0 cset name='SLIM RX1 MUX' AIF1_PB
        amixer -c 0 cset name='RX1 MIX1 INP1' RX1
        amixer -c 0 cset name='RX1 INTERP' 'RX1 MIX2'
        amixer -c 0 cset name='CLASS_H_DSM MUX' DSM_HPHL_RX1
        amixer -c 0 cset name='HPHL DAC Switch' 1
        amixer -c 0 cset name='HPHL Volume' 70%

   **Loose ends.** The controller logs `Error Interrupt received 0x82000000`
   during stream setup. `SLIM RX3`..`RX7 MUX` warn "has no paths", which is
   expected while only RX1/RX2 are routed. Capture is absent entirely - the
   driver registers one playback DAI - so "Not able to allocate memory for 0
   slimbus tx ports" is not a fault.

   **Boot gets slow if the codec is blacklisted**, because the card's dai-links
   then wait on a device that never arrives; one boot took about seven minutes and
   another had to be power-cycled. With the codec loading normally that goes away.
   If it ever has to be blacklisted again, drop the `sound` node with it.

## Vibrator

`0040`, one line. Mainline already has the driver (`pm8xxx-vibrator.c`), the config
already had `CONFIG_INPUT_PM8XXX_VIBRATOR=y`, and `pm8941.dtsi` already carries
`pm8941_vib: vibrator@c000` with the right compatible - it is just left
`status = "disabled"`, and no msm8974 board in the tree enables it. Both stock and
LineageOS run this exact node (`qcom,vib@c000`, `qcom,qpnp-vibrator`, okay), so the
hardware is there.

**SOLVED 2026-09-15: the motor runs and was felt.** On r84 `pm8xxx_vib_ffmemless`
is `event0`, the driver is bound at `fc4cf000.spmi:pm8941@1:vibrator@c000`, the node
advertises `FF_RUMBLE`, and an `EVIOCSFF` upload followed by an `EV_FF` play produces
a burst you can feel. That last step is the whole point: an ff-memless device
enumerates whether or not a motor is wired to that PMIC output, so enumeration on r83
proved nothing and only playing it could.

**That test is now written: `tools/ff-test.py`.** It needs no compiler on the phone -
it packs the struct and the ioctl numbers itself - and it scans `/dev/input`, reports
which node advertises `FF_RUMBLE`, then uploads and plays three bursts at different
magnitudes. Its scan half is already exercised against r56, where it correctly finds
`gpio-keys`, `pm8941_pwrkey` and the Synaptics touchscreen and no FF device at all;
what is untested is the upload, which needs the vibrator present.

`sizeof(struct ff_effect)` is **44** on arm32, not 40 - `custom_len` in
`ff_periodic_effect` is a `__u32`, which makes the union 28 bytes on top of a 16-byte
header (14 bytes of shorts, padded to 16 for the union's alignment). `EVIOCSFF`
encodes that size in the ioctl number, so getting it wrong does not fail cleanly: it
returns `EFAULT`, which reads like a driver bug rather than an arithmetic one. The
correct number is `0x402c4580`, and the script asserts its own packing.

`pm8xxx-vibrator` accepts **`FF_RUMBLE` only** and takes its level from
`strong_magnitude >> 8`, so `0xffff` is full scale and anything below `0x0100` rounds
to a stop.

Enabled on amami only rather than rhine-wide, since honami and togari cannot be
tested here.

## Camera: bigger than audio

Surveyed, not started. Mainline's CAMSS driver matches `qcom,msm8916-camss`,
`msm8953`, `msm8996`, `sc7280`, `sc8280xp` and `sdm660` - **there is no msm8974
support**, so it would need a new resource table and version alongside those.

Worse, the sensors are not described in any standard way. Stock binds
`qcom,camera@20` and `@6c` as `qcom,sony_camera_0` / `_1`, Sony's own binding, with
the actual parts identified only by module codes and per-module power sequences -
`SOI08BS2` and `SOI20BS0` at the rear, `LGI02BN1` and `SEM02BN1` at the front. So
even after CAMSS, each module needs identifying and a sensor driver wiring up.

That makes camera the largest single area left, ahead of audio.

## Parked patches

Out of the build, kept because the data in them was expensive to recover:

- `0034`, `0035`, `0036`, `0037` - the GPU and MDP IOMMUs, and the page-size fix.
- `0018`, `0025` - the earlier `qcom_iommu` node and the GPU's binding to it.
- `0027` - the non-secure BFB settings.
- `0031` - subscribing to every data type. Now known not to be a proximity fix:
  proximity *is* the primary type. It would be the route to an ambient light
  channel, which does work at the SMGR level.
- `0046` - answering unmapped registry groups with zeroes instead of failing.
  Tried on hardware, changed nothing.
- `debug/9004` - dumps the whole SMMU state after a successful attach.

In the build but inert without those: `0017` (optional secure id), `0019` (the `alt`
clock, which is what stopped the first attempt hanging the phone), `0026` (detaching
the ARM DMA mapping).

Check `glxinfo -B` reports `FD330` after touching any of this, not merely that the
screen lights up: a broken IOMMU shows up as a silent fallback to `llvmpipe`.

## Smaller loose ends

- The CPU wedge is fixed but only partly explained: the two observed failures had
  different signatures, so there may be a second bug behind the first.
- `reboot bootloader` is a dead end - S1Boot ignores the Qualcomm magics at `0x65c`.
  Getting to fastboot still means holding Volume Up while plugging in.
- ~~`BAT_THERM` sits at 642 mV...~~ **Resolved, and the extended band is correct
  rather than a workaround.** Calibrated from the VADC's own references
  (97.37 uV/count) against `VDD_VADC` = 1781.7 mV, the thermistor reads **606.5 mV at
  rest, 34.0% of the reference**. The narrow jeita floor is 35% = 623.6 mV, so this
  battery reads *below* it at ordinary room temperature - the narrow band inhibits
  charging permanently, not marginally. The extended floor is 25% = 445.4 mV.
  Ten minutes of four-core load moved it to 562.7 mV for a +7.1 C rise in PMIC die
  temperature, about **-6.2 mV/C**, and the battery kept cooling more slowly than the
  SoC afterwards, so it warmed less than 7 C and the true per-battery-degree slope is
  steeper still. Either way there is roughly 26 C or more of headroom before the
  extended hot threshold trips, which puts it near 50 C - about where a charger should
  stop anyway. Nothing to fix.

  The underlying reason is that the PM8941 BTC thresholds are fixed percentages of the
  thermistor reference, sized for Qualcomm's reference battery, and amami's sits
  lower. Worth knowing: **mainline has no `SCALE_BATT_THERM`.** Downstream declares
  this channel with `qcom,scale-function = <1>` (a dedicated battery-thermistor
  table); mainline only offers `DEFAULT`, `THERM_100K_PULLUP`, `PMIC_THERM`,
  `XOTHERM` and the HW_CALIB variants. That is why `LR_MUX1_BAT_THERM` has no
  `_input` attribute and why `qcom_smbb` reports no battery `temp` at all.
  Follow-up worth one boot: declare the channel with `SCALE_THERM_100K_PULLUP` and
  check the reported temperature against a cold and a warm reference. If the battery's
  NTC is a 100k part the existing table may be close enough to give a real `temp`.
- `THERMAL_EMULATION` is still enabled. It is how the thermal trips were tested, and
  it also lets root feed the thermal core a fake low reading. Worth dropping once the
  frequency ceiling can reach 75 C honestly.
