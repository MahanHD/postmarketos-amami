# Next steps

Rewritten 2026-09-12, after a long session that fixed a core-wedging bug of our own
making, produced the first power numbers, and then solved the GPU IOMMU.

The headline change since the last version: **the GPU IOMMU works**, and the thing
that cracked it was not another build. Five rebuild-and-guess cycles had failed;
reading the SMMU's own registers on a running phone through `/dev/mem` found both
bugs in one sitting. Prefer instrumenting the hardware over rebuilding it.

## Start here

**Device state: r85 is flashed and running.** Flashed 2026-09-15, verified by
readback, confirmed booting from flash. It is r84 plus SLIMbus (`0042`-`0044`),
and the Taiko enumerates on the bus. Nothing is half-applied.

**Mind the numbering: `pkgrel` + 1 is what `uname -v` prints.** r84 reports `#85`
and r85 reports `#86`, which is an easy way to think you booted the wrong thing.

r84 (`#85`) remains the fallback worth keeping - it is the last build whose every
feature was tested - and its image is still at
`boot-images/boot-r84.img`, md5 `d4550bf58700118ce0b3ee31aee67999`.

    boot partition:  /dev/disk/by-partlabel/boot  ->  mmcblk0p14  (20971520 bytes)
    r85, flashed now:  a9bb0fcb4c1b0e9624fbb6ff8bf3f48b  (18225152 bytes)
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

Not working: audio, proximity, ambient light, deep suspend.

The vibrator **works** as of `0040` - felt, not merely enumerated - and the ADSP
audio transport is up as of `0039` with all four Q6 services attached as of `0041`.
Audio still makes no sound: the codec driver is the blocker, see below.

The GPU IOMMU works as of `0034`-`0036`. The MDP half (`0037`) reclaims the 192MB
carveout but blanks the panel, and all of it is out of the build.

### Where the build recipe actually is

Worth stating because it lives on disk in pmaports, not in this repo, so nothing here
records it and a new session would have to look:

- **Flashed on the phone: r56** - none of the IOMMU work, no audio, no vibrator. This
  is the known-good kernel and the one to come back to. Boot partition md5
  `69b89a70e0a216cc128579bea40f5561`.
- **pmaports recipe: r84** - `0001`-`0029` as usual, plus `0039` (APR), `0040`
  (vibrator) and `0041` (the q6asm frontend DAIs), with `CONFIG_QCOM_APR` and the
  `SND_SOC_QDSP6_*` symbols on. No IOMMU patches,
  `# CONFIG_ARM_SMMU is not set`. Built, and the boot image is staged at
  `~/Devices/Xperia-Z1-Compact/boot-images/boot-r84.img`.
- So **the recipe and the flashed kernel differ**. Rebuilding and installing without
  noticing would quietly add APR and the vibrator. That is harmless, but it is not
  what is on the phone.
- Apks r57-r84 in `~/.local/var/pmbootstrap/packages/` are a mix of experiments;
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

### Why sensor 0x28 reports nothing

Proximity enumerates correctly and registers an IIO device - which is why it passed
for working - and then never delivers a sample. Zero bytes in 25 s with a hand over
it, against tens of kilobytes in five from the accelerometer.

Already ruled out: that only the primary data type is subscribed. True, and it is why
an ambient light channel alone can never work, but subscribing to both (`0031`) leaves
it just as silent.

Where to look: the APDS-9930 configuration in a working ROM; what actually sits at the
unmapped registry offsets; and whether any other msm8974 device in postmarketOS has
proximity working - if one does, the diff is the answer. Upstream lists proximity as
supported, which points at this device's configuration rather than the driver.

Weak lead, resist without a source: nine registry groups are requested and unmapped
(2001, 2500, 2610, 2650, 2680, 2970, 2971, 2980, 2990), and `group_map[]` leaves
`0x2900`-`0x2cff` unused - four pages against four unmapped `29xx` groups. `0007`
proved one missing group can disable a sensor, but that cost the accelerometer its
*enumeration*, and proximity enumerates fine.

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

3. **The WCD9320 driver.** New, large, and the only route to actual audio.

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
- `0031` - subscribing to every data type, a prerequisite for ambient light.
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
