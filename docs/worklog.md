# Working log

The chronological record of the port: what was tried, in what order, with the
measurements. It is long and partly superseded by later entries; the current
state and the plan are in `next-steps.md`, and the settled findings in `notes.md`.


Rewritten 2026-09-12, after a long session that fixed a core-wedging bug of our own
making, produced the first power numbers, and then solved the GPU IOMMU.

The headline change since the last version: **the GPU IOMMU works**, and the thing
that cracked it was not another build. Five rebuild-and-guess cycles had failed;
reading the SMMU's own registers on a running phone through `/dev/mem` found both
bugs in one sitting. Prefer instrumenting the hardware over rebuilding it.

## Start here

**Device state as of 2026-10-04 (evening): r181's modules are installed on r178's boot image**
(`uname -v` `#179`; the camera is all modules, so the boot image did not need reflashing).
r181 adds `0096` and `debug/9013` to r178. **The rear camera has produced its first real
photo** - see Camera, "First image". On the phone,
`/etc/modprobe.d/camss-bringup.conf` blacklists `qcom_camss`, `i2c_qcom_cci`, `imx219` and `ccs`
(each with `install ... /bin/false`), so nothing camera-related loads at boot. Load by hand
with `modprobe --ignore-install <module>`. `dtc` is installed on the phone (the host has none),
which is how the one-off lane-map DTBs below were made. Remove the blacklist once capture works.

**Previous state, 2026-10-02 end of day: r140 was flashed and installed**, `uname -v`
prints `#141`. This is the cleaned-up end state of the suspend work: `0072`-`0076` plus
`0079`-`0081`, with `0077`, `0082`, `0083`, `0084` and `debug/9005` all out. So **CPU
hotplug online works** and `mem_sleep` is back to `[s2idle]` alone. Verified after the
cleanup: `mem_sleep` offers only s2idle, nothing registers a suspend SAW, no vMPM debug
output, `cpu-spc` idle collapse live, and all-secondaries-off-and-back still works
(`nproc` 4 -> 1 -> 4, cpu3 executing +295 jiffies, `boot_id` unchanged).

`mem_sleep_default=s2idle` stays on the command line even though nothing registers suspend
ops now, so it is inert - it is kept as insurance in case `0077` is ever unparked.

One cosmetic leftover from the day's three hard resets: `/boot` (the ext2 loop image)
mounts with `EXT4-fs (loop0p1): warning: mounting unchecked fs, running e2fsck is
recommended`. Harmless, and `boot-deploy` rewrites that image on every kernel install
anyway.

**Historical, r134:**, so the boot image
and `/lib/modules` agree and `uname -v` prints `#135`. r134 is `0072`-`0077` plus
`0079`-`0081`: **CPU hotplug online works**, and **`PM_SUSPEND_MEM` completes and
resumes on all four cores** - though it does not yet save power, because the collapse
itself is still unwritten. `mem_sleep` reads `[s2idle] deep`, s2idle by default. Images kept in `boot-images/`, newest first:

        r178  (boot)     c93cd24b55bb9ef4074f911c1147371f   0094 with vt lanes = 4, 9011 out, + debug/9012
        r171             e829711c11c0fc0eb098d9f6644d683c   + 0094 IMX200 quirk, 0095, debug/9011
        r171-swap        b7bc347f6667864a66c928a8490e736a   test only: CSIPHY lanes 0 and 4 swapped
        r170-1lane       cff4cf465a2ce8ed205eb43e15565c98   test only: sensor on one lane
        r167             fe9aca311b7eb10ecafd461249704862   + 0092 binner/pixel-array init_state
        r166             dd74363c4b64b7f35e60d34d86fbb42b   CCS binds the rear sensor, 0091
        r163             563359e44491475d0d08accc54fb7449   9007 switched to nokia,smia
        r162             e428c13cc495bea4acbae4d485bb8115   + CONFIG_VIDEO_CCS=m
        r161             3293fbdc75da5cf10056140083181dec   + 0090 MCLK table, front back at 19.2 MHz
        r160  2a2e62f2881e680aec0f3f21e540721c   0090 test: front asks 24 MHz, gets 48
        r159  5fc1ac44acace45d83ce73aab5bf9d72   + 9010 full-size frames, 0089 GPU purge fix
        r157  81039a43b0dd14ee729b7c4c7f92c18c   + test-pattern capture works (9009)
        r156  9195531fb31c6af2b10f56b24421c461   + front camera in the ID read too
        r155  873073854109d963aa45110d48846a36   + sensor ID / EEPROM read (9007/9008)
        r148  9d8ce1923c5d4b14fee46a67620b49c0   + camera bring-up, CAMSS probes
        r146  e4278675738079153632413baa2d1768   camss enabled, 465 MHz VFE bug still in
        r145  318a925f6ac5bfb44c6598e49111dde1   modular media config, camss node disabled
        r144  DO NOT BOOT  a23226c83a0d2a2d15b9b0a6c1a5b66d  built-in media config only
        r143  DO NOT BOOT  1f6c13c7e6c5fdb84d79a93f9f241b62  built-in media + camss, node off
        r142  DO NOT BOOT  13bc1982075978e9293d720c5f2f5f7d  built-in media + camss, node on
        r140  b6307908b71a609b4b40a5d236c7feea   0072-0076 + 0079-0081, clean
        r138  1d3b75ff257eac44cd23e5f1f3fc13a1   + 0083: CPU collapse WORKS, saves nothing
        r139  DO NOT SUSPEND DEEP  5fa270a0901a51136aa7f45213653b5a  + 0084: L2_OFF, hangs
        r137  176b6e2f1d90a1b2c2d19cba87068b49   0083 without the collapse probe
        r136  cee2aae351ab9691d09656364b059142   + debug/9005, the vMPM dump
        r134  82f8d601106f4ab8541076ea68245986   + 0077: deep suspend path works
        r135  DO NOT SUSPEND DEEP  639c7868e86cb43734ec60411f4c3980  + 0082: never wakes
        r133  1517dfe0422ab4517e55dfa4f4bbc02c   + 0079-0081: hotplug WORKS
        r132  fea23635de62cbe9cb9ee638277e49fa   + 0079,0080: survives, online fails
        r131  c137394c9a2be27ba0f2a7fb369a5074   + 0079 only: safe, online fails EIO
        r128  7eed4cecf1a5c16c8da822bf7d21f722   0072-0076, as r126
        r127  DO NOT BOOT  a0b235222e63d100a6f98371b169acc6  + 0078: resets the SoC
        r126  0072-0076, no suspend ops  (apk overwritten, see below)
        r125  cd88e313099ccfab02f18f69a451c614   + 0077, leaves the phone single-core
        r123  0b1481b0e20963c8cfa3e3b24849a667   spmi through the MPM
        r122  e54bb08747239bb0eaa78ff7518e03c4   tsens through the MPM, PMIC untouched
        r121  b8154484e19e74a88417326f19abf9b8   MPM bound, nothing routed
        r120  1a3b95afe7cdd8c795bed60c3219c819   L2 SAW only
        r119  73600a403efcdf28397441abccbc7099   before any suspend work
        r90   c2f94594ff341f68e5a1ce5aa04a1abd   long-standing fallback

r122 is the one to fall back to if anything about the PMIC interrupt turns out to
be wrong, since it has the MPM working but leaves SPMI on the GIC.

**r127 is kept only as evidence and must not be booted.** Offlining a core on it is
fine; onlining one hard-resets the phone. r128 exists because `0078` had to come back
out, and it is byte-for-byte r126's patch set at a new `pkgrel`.

**One bookkeeping casualty worth knowing about:** `r126.apk` in the pmbootstrap
package dir was rebuilt *with* `0078` before the `pkgrel` was bumped, so that apk no
longer matches `boot-images/boot-r126.img`, which is the genuine pre-`0078` image. The
image is the trustworthy artifact; the apk of that number is not. Bump `pkgrel`
**before** building, not after.

They do not always agree, and that is not a mistake when they differ: the codec
is `CONFIG_SND_SOC_WCD9320=m`, so codec patches ship in `snd-soc-wcd9320.ko` and
an `apk add` is enough. A `dd` to the boot partition is only needed when a `=y`
driver or the device tree changes - which `0068` (capture dai-links), `0070`
(`CONFIG_CHARGER_QCOM_SMBB=y`) and `0071` all did.

**The codec reloads now, so stop rebooting between codec builds.** `0065` and
`0066` fixed the unload and the reload respectively, and the whole cycle is:

    D=/sys/bus/platform/drivers/msm-snd-apq8096
    sudo sh -c "echo sound > $D/unbind"      # frees the module
    sudo modprobe -r snd_soc_wcd9320
    sudo apk add --allow-untrusted /tmp/linux-...apk
    sudo modprobe snd_soc_wcd9320
    sudo sh -c "echo sound > $D/bind"

The unbind is not optional - the card holds a reference and `modprobe -r` fails
with "Module snd_soc_wcd9320 is in use" without it, which silently turns the
following `modprobe` into a no-op and leaves you measuring the *old* instance.
That wasted two full test cycles; assert `lsmod | grep -c` is 0 before
reloading.

**The codec is blacklisted** in `/etc/modprobe.d/wcd9320-test.conf`, so after every
reboot the card does not exist until you run `sudo modprobe snd-soc-wcd9320`. An
empty `/sys/class/sound/` is that, not a regression. The blacklist dates from r89,
when loading the codec oopses while building the card; `0052` fixed that oops and
it now loads cleanly, so the file can go whenever the manual step stops being
useful. Everything else is unaffected. All five sensors - accel, gyro, mag, proximity
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

Rewritten 2026-10-01. The old list named the codec driver, deep suspend and
proximity; the driver exists, proximity works, and deep suspend has acquired a
prerequisite.

1. **The microphone**, and it is now a prerequisite rather than a feature. Every
   capture-side measurement on this codec is currently uninterpretable because
   nothing is known to put non-zero data on a SLIM TX port - the RX-to-TX loopback
   via `RMIX1` was tried and cannot be read for exactly that reason (Phase 3). A
   working mic is the only available positive control. `0067` and `0068` give the
   PCM; what is missing is micbias, the ADC enable and the decimator input muxes.

   Two board facts already extracted, from downstream's `qcom,audio-routing`:
   `AMIC1 <- MIC BIAS1 External <- Handset Mic` is the main mic, and the
   loudspeaker is **bridged LINEOUT1-4**, not SPK DRV. And one trap: the
   decimator muxes are not symmetric - `dec1_mux_text` is
   `{"ZERO", "DMIC1", "ADC6"}`, so DEC1 cannot take ADC1 at all; ADC1 is offered
   only to DEC6 and DEC7. Assuming DEC*n* pairs with ADC*n* would be wrong.
2. ~~**CPU hotplug online**~~ **SOLVED 2026-10-02**, `0079`+`0080`+`0081` on r133.
   Power-collapse the dying core through its SPM, re-run the release sequence on a
   re-online, and let a recalled core leave the collapse loop so ARM's resuscitate
   path can take it into `secondary_start_kernel`. See Phase 2. This unblocks (3).
3. **Deep suspend: the CPU collapse works (`0083`, r138); the L2 half does not.** The
   mem route completes, the CPU genuinely power-collapses and resumes 3/3, and the vMPM
   wakeup set is proven correct. `L2_OFF` still hangs the phone (`0082`, parked). Two
   things left, in order: **measure the power saving** - it is completely unmeasured and
   needs USB unplugged, so it needs a person - and then split `0082`'s two variables to
   find which of `L2_OFF` or `0072`'s L2 SAW PC sequence is the one that hangs. Phase 2
   has both experiments written out.
4. **Camera**, still the largest untouched area and still its own project.

Smaller, self-contained: wire a battery `temp` consumer if anything wants one,
drop `THERMAL_EMULATION` once the frequency ceiling can reach 75 C honestly, and
the unexplained half of the CPU wedge (two failures, different signatures).

### Two traps worth not rediscovering

- **`/sys/kernel/debug/regmap/0-01/registers` is unusable on pm8941.** Every register
  is a separate SPMI transaction and the file walks the whole address space, so even
  a `head -c` of the first few hundred KB does not return, and the reader is
  effectively unkillable while it runs. Three attempts pushed load average past 5.
  The SMBB notes elsewhere in this file describe reading `0-00` that way - treat that
  as "for a small range, patiently", not as a general technique.
- **pstore/ramoops retains nothing on this device, so it cannot be used for
  post-mortem.** The DT reserves `ramoops@3e8e0000` and the kernel says
  `printk: legacy console [ramoops-1] enabled` and `Registered ramoops as persistent
  store backend`, which all looks like a working black box. `/sys/fs/pstore` is
  nevertheless **empty after an ordinary clean reboot** - that control was run on
  2026-10-01. An empty pstore after a crash therefore says nothing whatever about how
  the machine went down. Reasoning from its emptiness produced one wrong conclusion
  here already (a confident "DDR lost its contents", withdrawn). If a post-mortem is
  ever actually needed, make ramoops work first and prove it with a deliberate
  `sysrq-trigger` crash.
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

- **Current, 2026-10-03: the phone and the pmaports recipe are both r148.** The camera
  needs these in `config-postmarketos-qcom-msm8974.armv7`, and **they must stay modular** -
  built in, the same symbols stop the kernel booting (see Camera):

        CONFIG_MEDIA_SUPPORT=m
        CONFIG_VIDEO_DEV=m
        CONFIG_VIDEO_QCOM_CAMSS=m
        CONFIG_I2C_QCOM_CCI=m
        CONFIG_VIDEO_CAMERA_SENSOR=y
        CONFIG_VIDEO_IMX219=m          # bring-up only, borrowed by debug/9007-9008
        CONFIG_VIDEO_CCS=m             # the generic SMIA/CCS driver both sensors bind to
        CONFIG_MEDIA_CAMERA_SUPPORT=y
        CONFIG_MEDIA_CONTROLLER=y
        CONFIG_MEDIA_PLATFORM_SUPPORT=y
        CONFIG_MEDIA_PLATFORM_DRIVERS=y
        CONFIG_V4L_PLATFORM_DRIVERS=y
        # CONFIG_MEDIA_SUPPORT_FILTER is not set
        # CONFIG_MEDIA_ANALOG_TV_SUPPORT is not set
        # CONFIG_MEDIA_DIGITAL_TV_SUPPORT is not set
        # CONFIG_MEDIA_RADIO_SUPPORT is not set
        # CONFIG_MEDIA_SDR_SUPPORT is not set
        # CONFIG_MEDIA_TEST_SUPPORT is not set
        # CONFIG_MEDIA_SUBDRV_AUTOSELECT is not set

  The bool menus have to be switched off explicitly. The recipe copies the config and runs
  `make` with no `olddefconfig`, so `syncconfig` fills every newly-visible symbol with its
  default - and the defaults for those menus are on.
- **Historical: flashed on the phone at r90**, and the pmaports recipe was also r90, so they
  agreed. It is `0001`-`0029` as usual plus `0039` (APR), `0040` (vibrator),
  `0041` (q6asm DAIs), `0042`-`0044` (SLIMbus), `0045`, `0047` and `0048`, with `CONFIG_QCOM_APR`, the
  `SND_SOC_QDSP6_*` symbols and `CONFIG_SLIMBUS` on. No IOMMU patches,
  `# CONFIG_ARM_SMMU is not set`.
- **`uname -v` prints `pkgrel` + 1.** r85 reports `#86`. Easy to misread as having
  booted the wrong build.
- Earlier images are kept in `~/Devices/Xperia-Z1-Compact/boot-images/`: r84
  (`d4550bf58700118ce0b3ee31aee67999`) is the last build before SLIMbus, and
  r56-rebuilt (`69b89a70e0a216cc128579bea40f5561`) reproduces what was flashed for
  most of this port's life.
- Apks r57-r86 in pmbootstrap's `packages/` directory are a mix of experiments;
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

**UNBLOCKED 2026-10-02: the mem path now completes and resumes on all four cores.**
With `0079`-`0081` fixing hotplug and `0077` unparked, r134 does this:

        PM: suspend entry (deep)
        Disabling non-boot CPUs ...
          CPU1/2/3: going down by SPM power collapse
        Enabling non-boot CPUs ...
          CPU1 is up / CPU2 is up / CPU3 is up
        PM: suspend exit

`rtcwake -m mem -s 20` returned 0, `suspend_stats/success` = 1, `fail` = 0, resumed
with `nproc=4` and `boot_id` unchanged, 28 s elapsed across the 20 s alarm. WiFi
reconnected on its own. Compare the original failure below, which resumed single-core.

**What this does NOT yet mean: there is no power saving.** `0077`'s `.enter` is still
only `cpu_do_idle()`, deliberately, so the SoC does not actually collapse - the PM core
parks the secondaries and `syscore_suspend()` hands vMPM to the RPM, but the CPU and L2
SAWs stay in their idle modes and no `qcom_scm_cpu_power_down(L2_OFF)` is issued. So
what is proven is that the whole *path* works and is safe to stand on, not that it
saves anything. **The remaining job is the collapse itself**, in `spm_suspend_enter()`,
where `drv` is already the cluster's SAW: put the SAWs into `PM_SLEEP_MODE_PC` and
issue the SCM power-down. Until that lands, `deep` costs the same as `s2idle`.

**`mem_sleep_default=s2idle` is now on the kernel command line** (in
`tools/mkbootimg.py`), which is what makes unparking `0077` safe. The kernel's own
default is `PM_SUSPEND_MEM`, so registering any `platform_suspend_ops` would otherwise
make `deep` the default and send every ordinary idle suspend down the collapse path.
With the guard, `/sys/power/mem_sleep` reads `[s2idle] deep` and `deep` is opt-in.

A loose end seen on resume turned out to be pre-existing: a single
`[drm:mdp5_irq_error_handler] *ERROR* errors: 04000000` about six seconds after the CPUs
come back. **Control run 2026-10-02: the identical error appears after an `s2idle`
resume too**, so it is not specific to the deep path and not a regression from `0077`.
Still unexplained, but old.

### The collapse: tried as `0082`, and the phone did not wake

`spm_suspend_enter()` was filled in - the boot CPU's own SAW and the L2 SAW both to
`PM_SLEEP_MODE_PC`, then `cpu_suspend()` into
`qcom_scm_cpu_power_down(QCOM_SCM_CPU_PWR_DOWN_L2_OFF)`, and both SAWs back to standby
on the way out. Built as r135, flashed, and `rtcwake -m mem -s 20`:

        --- rtcwake -m mem -s 20 WITH the SoC collapse
        rtcwake: wakeup from "mem" using /dev/rtc0 at ...
        (nothing further, ever)

The phone stopped answering and **was not enumerated on USB at all** - no Sony device,
no usb net interface, no ping. It needed Power+VolUp. So the SoC did collapse; it simply
never came back. The same alarm on r134, where nothing actually powers down, resumes
reliably.

**There is no post-mortem evidence, and that needs saying plainly.** The on-disk log
stops at the line before the suspend; `suspend_stats` is reset by the reboot; and
pstore/ramoops retains nothing on this device (see the traps). So what follows are
*hypotheses*, and this file should not be read as though one of them were established:

- **(a) the wakeup is never armed for a real collapse.** On r134 the SoC stays powered,
  so a wake can arrive by any route; under a genuine collapse the GIC is off and every
  wake has to come through the MPM and the RPM. The vMPM flush in `0076` runs, but
  whether the RPM honours the set has never been exercised with the SoC actually down.
- **(b) the collapse or its resume is broken with the L2 off.** `QCOM_SCM_CPU_PWR_DOWN_L2_ON`
  is used thousands of times a second by cpuidle and works; `L2_OFF` has never been used
  on this port, and the L2 SAW's own PC sequence from `0072` has never actually run.

Two things were checked in source and **neither settles it**, recorded so they are not
re-checked:

- `qpnpint_irq_set_wake()` in the SPMI arbiter *does* forward to the arbiter's summary
  interrupt (`irq_set_irq_wake(bus->irq, on)`), which `0075` routes to MPM pin 62. So the
  chain from a PMIC interrupt up to the MPM exists. That refutes the first guess made.
- `rtc-pm8xxx` calls only `devm_device_init_wakeup()` and never `enable_irq_wake()` or
  `dev_pm_set_wake_irq()`, which looks like the alarm is not armed as a system wake
  source at all. But that cannot be the whole story, because on r134 the alarm *did* wake
  the phone - 28 s elapsed for a 20 s alarm, so it really stayed down. Suggestive, not
  conclusive.

### Both hypotheses tested 2026-10-02, and the CPU half now works

**(a) is refuted: the wakeup set is armed correctly.** `debug/9005` dumps the MPM
`ENABLE` words at the instant `syscore_suspend()` hands vMPM to the RPM, on a kernel
that does wake. During a `mem` suspend:

        mpm: vMPM ENABLE[0] = 0x00000004   (pin 2  = tsens)
        mpm: vMPM ENABLE[1] = 0x40000000   (pin 62 = SPMI, so every PMIC wakeup)

Pin 62 is set, and sysfs agrees (`irq 37: mpm hwirq=62 wakeup=enabled`, fed by a
wake-armed `pmic_arb` child). `mbox_send_message()` must also have succeeded, since
`0076` aborts the suspend otherwise and the suspend reported success. So the
`IRQCHIP_MASK_ON_SUSPEND` worry does not bite, and the wakeup side is **not** the
problem.

**(b) is where the fault is, and the CPU half of the collapse works.** `0083` is `0082`
with `QCOM_SCM_CPU_PWR_DOWN_L2_ON` instead of `L2_OFF`, and with the L2 SAW left alone.
On r138 it collapses and resumes, three rounds out of three:

        round 1: rc=0 elapsed=23s nproc=4 boot_id_same=YES
          spm: suspend collapse happened (cpu_suspend returned 0)
        round 2/3: the same, success=3 fail=0

**`cpu_suspend()` returning 0 is the load-bearing part of that**, and it is why the
probe exists: `spm_pm_collapse()` returns -1 if an interrupt beats the power-down, and a
suspend that merely fell through still resumes and still reports success. Without
reading that return there is no way to tell a real collapse from nothing happening.

**What is still unmeasured: whether this saves power.** The collapse demonstrably
happens, but current draw needs USB unplugged (see the battery notes), so the saving is
unquantified. Measuring it against the 214 mA s2idle costs is the obvious next thing and
it needs a person to pull the cable.

**`L2_OFF` is the culprit on its own, and the L2 SAW is exonerated.** `0082` had changed
two things at once - the SCM flag *and* arming the L2 SAW for `PM_SLEEP_MODE_PC` - so
`0084` isolated the first: `L2_OFF` with the L2 SAW deliberately left in standby. It
hangs too. The table:

        patch   SCM flag   L2 SAW      result
        0082    L2_OFF     armed PC    hangs, no wake
        0083    L2_ON      standby     WORKS, 3/3, collapse confirmed
        0084    L2_OFF     standby     hangs, no wake

So `L2_OFF` fails regardless of what the L2 SAW is doing, and `0072`'s L2 PC sequence is
not implicated. That also kills most of the value of the other half of the split
(`L2_ON` + SAW armed): it would only say whether the SAW is *additionally* harmful, which
no longer matters for getting a working collapse.

**A hypothesis for why, explicitly not established** - there is no post-mortem for a hang
(pstore keeps nothing): this port has no L2 retention or restore path for a genuine L2
power-down. `L2_ON` works because the L2 stays up and TrustZone only has to save and
restore the core, which is the same thing it does for every cpuidle collapse and every
`qcom_cpu_die()`. `L2_OFF` additionally requires the secure side to deal with L2 contents
and bring the cache back, and either this device's TZ firmware does not support that for
the AP or it needs setup never done here - downstream drives L2 power-down through its
own RPM and SPM sequencing that mainline has no equivalent of.

**So the realistic end state for this port is `0083`:** a real CPU power collapse at
system suspend with the L2 left on. Verified, by `cpu_suspend()` returning 0, to be an
actual collapse rather than a fall-through. Whether it is worth having is exactly what
the power measurement answers, and that measurement is now the open question rather than
any more collapse variants.

### Measured 2026-10-02: the collapse saves nothing, because cpuidle already did it

One unplugged session, 20 minutes in each mode back to back on the same battery:

        mode                    duration   dV        dcapacity
        s2idle                  1208s      38.0 mV   3%
        deep (CPU collapse)     1203s      41.8 mV   4%

`deep` came out marginally *worse*, which is inside the ordering confound - it ran second
and so from a lower state of charge, where the curve is steeper. The honest reading is **no
measurable saving**, not that it costs more. The collapse definitely happened: the run
logged `spm: suspend collapse happened (cpu_suspend returned 0)`.

**And the reason is plain, which makes this a conclusive negative rather than a weak
one.** cpuidle on this SoC *already* power-collapses the CPU:

        /sys/devices/system/cpu/cpu0/cpuidle/
          state0: name=WFI      usage=18572
          state1: name=cpu-spc  usage=23781  time=516738346us

`cpu-spc` is the SPM driver's `PM_SLEEP_MODE_SPC` plus
`qcom_scm_cpu_power_down(L2_ON)` - the identical sequence `0083` runs at suspend - and the
idle governor enters it tens of thousands of times a boot. So in s2idle the cores are
already collapsing whenever idle, and doing it once more at suspend entry adds nothing.
The CPU core was never where the suspend power was going.

**Which means `deep` offers nothing on this port.** `L2_ON` is no better than s2idle
(measured) and `L2_OFF` does not wake (`0082`/`0084`). The remaining power is in the rest
of the SoC - L2, DDR, clocks, regulators, the RPM's own vote set - and reaching it needs
the full-SoC collapse that `L2_OFF` was the route to. The 214 mA figure recorded earlier
is consistent with that: it is the SoC, not the Kraits.

**So the suspend work is finished for now, and the honest summary is that it fixed a real
bug and produced no power win.** What is worth keeping is `0079`-`0081`, because CPU
hotplug online was broken on its own terms, and `0072`-`0076`, which are correct and leave
the MPM bound and the wakeup set armed. `0077` and `0083` give a working `deep` that is
measurably no better than the default - keep them parked rather than shipped, since a
`deep` mode nothing should select is risk without benefit.

**Historical note on the instruments, kept because it shaped the method.** There is no coulomb
counter: `smbb-bif` offers only `capacity`, `voltage_now` and `temp`, and `capacity` is
voltage-derived, which at 94% sits in the flat part of the curve. The only current
instrument is the IADC (`in_current0_raw`), and reading it needs the CPU awake, so it
cannot sample during a suspend. That leaves capacity drop over a long suspend, compared
against the already-measured 214 mA that the SoC costs in s2idle - about 9 %/hour on this
battery, so a 30-minute `deep` suspend should drop ~4-5 % if nothing improved and ~1 % if
the collapse is doing real work. One run, not two, since the s2idle baseline is already
known. It needs USB out, which also means the phone must be left asleep and unreachable
for the duration.

---

**Historical, 2026-10-01: deep suspend could not work until CPU hotplug online did.**
The first `PM_SUSPEND_MEM` attempt suspended and resumed correctly - and came back
on **one core**.

        Disabling non-boot CPUs ...
        Enabling non-boot CPUs ...
        CPU1: failed to come online     Error taking CPU1 up: -5
        CPU2: failed to come online     Error taking CPU2 up: -5
        CPU3: failed to come online     Error taking CPU3 up: -5
        post: online cpus=0     nproc=1

`suspend success=1`, `rtcwake` returned 0, the MPM flush did not abort anything.
The suspend worked. The CPUs did not come back, and nothing in userspace can
recover them - writing 1 to `cpuN/online` reports success in the file and changes
nothing; `/proc/cpuinfo` stays at one processor until a reboot.

**It is not the suspend path.** Plain hotplug, with no suspend anywhere near it:

        echo 0 > cpu1/online   ->  ok, nproc 3
        echo 1 > cpu1/online   ->  "write error: I/O error", CPU1: failed to come online

So this is a pre-existing mainline limitation on msm8974, and it blocks
`PM_SUSPEND_MEM` completely, because `pm_sleep_disable_secondary_cpus()` is
unconditional on that path - every mem suspend parks the secondaries whether the
platform can bring them back or not.

**The mechanism, established 2026-10-01 and no longer a guess.** The core never
wakes, and the reason is that its wakeup interrupt has been masked:

        __cpu_disable()
          -> ipi_teardown(cpu)
               for (i = 0; i < nr_ipi; i++)
                       disable_percpu_irq(ipi_irq_base + i);

`nr_ipi` covers the whole `ipi_msg_type` enum, and `IPI_WAKEUP` is the **first**
entry in it. So by the time the dying core reaches

        static void qcom_cpu_die(unsigned int cpu)
        {
                wfi();
        }

its own wakeup IPI is disabled at the GIC, and the `arch_send_wakeup_ipi_mask()`
that `qcom_boot_secondary()` sends can never be delivered to it. The `wfi()` never
returns, `cpu_die` never returns, and ARM's fallthrough into
`secondary_start_kernel` is therefore unreachable.

**The confirming observation is a missing message.** `arch_cpu_idle_dead()` prints
`smp_ops.cpu_die() returned, trying to resuscitate` before it falls through. On a
failed online we get

        CPU1: failed to come online

and **no** resuscitate line. That separates "woke up and then failed" from "never
woke at all", and it is the second.

**`cold_boot_done` is the other half, but fixing it the obvious way makes things
worse - this was tried.** The gate

        static DEFINE_PER_CPU(int, cold_boot_done);
        if (!per_cpu(cold_boot_done, cpu)) {
                ret = func(cpu);     /* kpssv2_release_secondary: the ACC/SAW init */
                per_cpu(cold_boot_done, cpu) = true;
        }

does run the ACC/SAW release sequence **once per CPU, ever**. `0078` dropped the
gate so it re-ran on every online, and made `qcom_cpu_die()` loop in `wfi()` so a
stray wake could not resuscitate behind the kernel's back. Built as r127, flashed,
and it **hard-resets the SoC** at the online, three times out of three:

        --- offline cpu1
          rc=0 online=0,2-3
          IRQ75/78/87: set affinity failed(-22)
        --- online cpu1          <- written and synced
                                 <- nothing further; SoC resets here

**Why, and it is the whole lesson.** `kpssv2_release_secondary()` is a *cold boot*
power-up sequence: `APC_PWR_GATE_CTL` (BHS on, LDO bypass), the L2 SAW's
`APCS_SAW2_2_VCTL`, then `CLAMP | COREPOR_RST` asserted and released. That is only
valid on a core that is **genuinely powered off**. `0078` left the core powered and
clocked in `wfi()`, so the sequence clamps and resets a live core with the L2 and
the fabric up; the bus hangs and the secure side resets the SoC. Re-running the
release is necessary but not sufficient - the core has to be off first.

**The fix is to power-collapse the dying core, not park it.** `qcom_cpu_die()` has to
take the core properly off, so that the cold-boot release sequence is operating on the
state it expects. That turns out to need **no new plumbing at all**, which corrects a
claim made here first time round: `spm_set_low_power_mode()` is *not* private to
`drivers/soc/qcom/spm.c`. It is declared in `include/soc/qcom/spm.h` and already
called from `drivers/cpuidle/cpuidle-qcom-spm.c`, and `QCOM_SPM`, `ARM_QCOM_SPM_CPUIDLE`
and `ARM_CPU_SUSPEND` are all `=y` here, so `platsmp.c` links straight against it with
no `EXPORT_SYMBOL` and no edit to `spm.c`.

So `qcom_cpu_die()` can reuse the exact sequence the idle path already runs thousands
of times a second on this device:

        spm_set_low_power_mode(drv, PM_SLEEP_MODE_SPC);
        cpu_suspend(0, qcom_pm_collapse);   /* QCOM_SCM_CPU_PWR_DOWN_L2_ON */
        spm_set_low_power_mode(drv, PM_SLEEP_MODE_STBY);

**SPC, not PC**, is the right mode: standalone power collapse leaves the L2 up, and the
other cores are still running out of it. The SPM driver data comes from the CPU's
`qcom,saw` phandle exactly as the cpuidle driver gets it.

**Split deliberately into two patches, because only the second one can reset the phone:**

- `0079` powers the dying core off and nothing else. The online still fails, because
  the release sequence is still gated by `cold_boot_done` - but it fails the old safe
  way, with `EIO`. Independently testable, and the test that matters is the negative
  one: offlining and then attempting an online must **not** reset the SoC.
- `0080` re-runs the release sequence on a re-online, gated on a per-CPU `parked` flag
  that `qcom_cpu_die()` raises just before the collapse. If the flag is not up within
  10 ms the online is refused with `-EBUSY` rather than risking the reset, since a
  refused online is a far better failure than a dead phone. The flag means "about to
  collapse" rather than "collapsed" - after the collapse the core executes nothing, so
  there is nothing left to set it - and the reader waits a further 100 us to cover the
  `cpu_suspend()` window.

**`0081` is the piece that actually made it work, and it was not predicted.** With
`0079`+`0080` on hardware (r132) the release sequence ran against a collapsed core and
the SoC **survived** - three cycles, `boot_id` unchanged, which is the direct
confirmation that the core being genuinely off is what makes the sequence legal. But
the core still never came online. The reason, and the diagnostic in `0079` is what
showed it:

        CPU1: back from collapse, wanted=1
        CPU1: smp_ops.cpu_die() returned, trying to resuscitate

The SPM cpuidle driver registers `cpu_resume_arm` as the **warm** boot address, so a
collapsed core powered back up does not arrive at the cold entry point at all - it
resumes *inside* `cpu_suspend()`, back in `qcom_cpu_die()`'s own loop, which set the
SPM to standby and collapsed it again. The core was bouncing in our loop and never
returned from `cpu_die`. `0081` adds a per-CPU `wanted` flag that
`qcom_boot_secondary()` raises before the release, and the loop returns when it sees
it - handing the core to `arch_cpu_idle_dead()`'s fallthrough, which is precisely what
that path exists for.

**SOLVED 2026-10-02 on r133 (`0079`+`0080`+`0081`).** Verified, with the reset check
done by comparing `/proc/sys/kernel/random/boot_id` rather than by reading uptime:

        cpu1/2/3 individually:  offline rc=0, online rc=0, online=0-3, state=238
        execution check:        pinned busy loop moved cpu1 +240, cpu2 +248, cpu3 +238
                                jiffies - the cores really run, not just show online
        all three off and back, 4 rounds:  nproc 4 -> 1 -> 4, 12/12 onlines rc=0
        boot_id identical throughout every test; 0 oops, 0 warnings

The all-at-once pattern matters more than the single-core one, because
`pm_sleep_disable_secondary_cpus()` parks every secondary and brings them all back -
and that is the pattern that reset r132 while `0081` was missing.

Superseded builds: r129/r130 were built before the `0079` diagnostic was added and were
never flashed; r131 is `0079` alone (safe, online fails with `EIO`), r132 is
`0079`+`0080` (survives, online still fails). Their apks may still be in the package
dir - r133 is the one that works.

**Two things that are *not* explained, recorded so they are not mistaken for
settled.** First, there is **no watchdog driver bound at all** on this device -
`/sys/class/watchdog` is empty and systemd's `RuntimeWatchdogUSec` is 0 - so whatever
resets the SoC, "a watchdog bit" is not the mechanism; that hypothesis was raised here
and is withdrawn. Second, the phone also hard-reset **once on r126, which has no
`0078`**, about 13 minutes after a failed online, in the middle of an `apk add`. On
r126 the failed online returns `EIO` without running the release sequence at all, so
that reset cannot have the same cause as r127's. A core left parked in `wfi()` may
leave the machine in a state that fails later, or it may be unrelated. One
observation, not reproduced, and pstore cannot help (see the traps).

**One thing offlining does that is survivable but worth knowing:** it strands a few
interrupts, `IRQ75/78/87: set affinity failed(-22)` (the numbers move between boots;
in one boot 75 was `msmgpio 62` SD card-detect, 79 `wcnss`, 85 `q6v5 wdog`). Those
are edge interrupts with zero counts, and the offline itself completes and the phone
keeps running. It is the online that kills it.

**`0077` is parked, not in the build**, and that matters for more than tidiness:
registering any `platform_suspend_ops` makes `deep` the **default** `mem_sleep`,
so it is not only a deliberate test that takes the new path - an ordinary idle
suspend would too, and would leave the phone single-core. Removed from the recipe
and the device is back to `mem_sleep: [s2idle]` on r126. `0076` stays in the build
and is inert, since syscore only runs on the mem path.

**What survives and is worth keeping:** `0072`-`0076`. The L2 SAW is programmed,
the MPM binds and flushes itself, and the PMIC's interrupt is MPM-routed and
armed. That is the whole wakeup side, and it is all still correct - it is the
*entry* side that is blocked. If CPU hotplug is ever fixed, `0077` plus the
collapse is a short step from here.

**Step 4 landed 2026-10-01 (`0075`): the wakeup path is complete.** The SPMI
arbiter now goes through the MPM on pin 62 instead of `GIC_SPI 190`:

        irq 37  hwirq=62  chip=mpm  wakeup=enabled    <- PMIC: power key, RTC, charger
        irq 46  hwirq=2   chip=mpm  wakeup=enabled    <- tsens

and nothing that depends on the PMIC broke: all three power supplies present,
battery reading 91% at 39.1C, `rtc-pm8xxx` bound, the pwrkey input device there,
and `udc ci_hdrc.0` still alive - which was the failure mode worth fearing, since
USB takes its VBUS state from the charger. Existing s2idle still works
(`rtcwake -m freeze -s 5` round-tripped, suspend count 1). r123 is
`0b1481b0e20963c8cfa3e3b24849a667`.

`wakeup=enabled` on pin 62 is the part that matters. The driver's mask/unmask
track the vMPM ENABLE bit, and the PM core disables non-wakeup interrupts on the
way into suspend, so at the moment the flush happens only wakeup sources will be
armed - which falls out of the existing plumbing rather than needing anything
written.

**What remains, and it is now only the suspend side:**

  1. **A caller for the genpd `power_off`.** `mpm_pd_power_off()` clears STATUS and
     does `mbox_send_message()` to hand vMPM to RPM. It is a genpd callback and
     nothing on this SoC calls it, so vMPM is never flushed to hardware. Either
     attach a consumer to that domain or add an entry point.
  2. **`platform_suspend_ops`** whose `.enter` puts the CPU and L2 SAWs in
     `PM_SLEEP_MODE_PC` and calls `cpu_suspend(0, ...)` with a collapse function
     passing `QCOM_SCM_CPU_PWR_DOWN_L2_OFF`. The pieces are all public: the L2's
     `spm_driver_data` via `of_parse_phandle`/`dev_get_drvdata` off the
     `l2-cache` node's `qcom,saw`, `spm_set_low_power_mode()` from
     `<soc/qcom/spm.h>`, and `qcom_scm_cpu_power_down()` which is exported.
  3. **GIC save/restore** across the collapse.
  4. **RPM sleep votes**, which is what turns a collapsed SoC into saved
     milliamps.

**Step 3 landed 2026-10-01 (`0074`): the MPM domain actually works.** tsens was
moved from `<GIC_SPI 184 ...>` to `interrupts-extended = <&mpm 2 ...>` and comes
back as

        irq 46   hwirq=2   chip=mpm   fc4a9000.thermal-sensor

with all thirteen thermal zones still reading 37-57C and no oops. `hwirq` being
**2** is the point: that is the MPM pin rather than the GIC number, so the
interrupt really is allocated in the MPM domain, and tsens still working proves
the domain forwards to its GIC parent correctly. r122 is
`e54bb08747239bb0eaa78ff7518e03c4`.

tsens was chosen deliberately as the first interrupt to move. It is level-high
like the one that matters, it is in downstream's map on pin 2, and it is harmless
if the routing is wrong - losing it costs thermal trip points, whereas getting the
SPMI arbiter wrong takes the PMIC, the charger, the RTC, the power key and the
USB extcon with it, which is a phone that needs fastboot and a physical cable
dance. With the mechanism now proven, moving SPMI is a much smaller bet.

**Step 2 landed 2026-10-01 (`0073`): the MPM binds.**

        /sys/bus/platform/drivers/qcom_mpm/interrupt-controller   bound
        supplier:platform:f9011000.mailbox                        mailbox resolved
        genpd "interrupt-controller"  off-0                       the flush hook exists

and nothing regressed - both remoteprocs running, WiFi connected, no oops. The
node is at root level following the `smp2p-*` pattern, with the vMPM slice added
to `rpm_msg_ram` as `apss_mpm: sram@1d0` sized **0x30**, not downstream's lazy
0x1000, which would have run straight over `mpss_master_stats` at 0xb50.
`CONFIG_QCOM_MPM=y`. r121 is `b8154484e19e74a88417326f19abf9b8`.

*It watches nothing yet, and that is the next step.* The MPM is a hierarchical
irq domain: a device only gets watched if its interrupt is allocated **through**
that domain. The wakeup-enabled interrupts are still straight GIC children -

        irq 37  hwirq 222  (spmi arbiter)      irq 46  hwirq 216  (tsens)

so making the power key a wakeup source means re-routing the SPMI arbiter's
interrupt from `<&intc GIC_SPI 190 ...>` to `interrupts-extended = <&mpm 62 ...>`.
That should be transparent while awake, since the MPM domain forwards to the GIC,
but it changes how the PMIC interrupt is wired in normal operation, so it wants
its own flash and its own check that the PMIC still works.

*Then* the remaining chain is unchanged: a caller for the genpd `power_off` that
flushes vMPM, `platform_suspend_ops` with GIC save/restore, and RPM sleep votes.

**Revised again, 2026-10-01: the MPM is a DT node plus a data translation, not a
driver port, and the wakeup we need is covered.** The blocker below stands - there
is no wakeup path today - but it is far more tractable than first assessed.

*The mainline driver already fits this hardware.* `irq-qcom-mpm.c` deliberately
does **not** touch physical MPM registers: it drives a shared SRAM region it calls
vMPM and then notifies RPM by mailbox, which copies vMPM into the real registers.
That is exactly 8974's shape - downstream's node carries
`reg = vmpm 0xfc4281d0, ipc 0xf9011008` - and the driver matches plain
`compatible = "qcom,mpm"`, so no new compatible is needed.

*The mailbox already works here.* `qcom,ipc-bit-offset = 1`, and `f9011008` is the
APCS block at offset 8. Mainline's msm8974.dtsi already has
`apcs: mailbox@f9011000` with `#mbox-cells = <1>`, `CONFIG_QCOM_APCS_IPC=y`, and
the remoteprocs already use it (`mboxes = <&apcs 10>` and friends). So the MPM
node just needs `mboxes = <&apcs 1>`.

*The pin map, decoded from downstream.* `qcom,gic-map` has 63 entries but **only
five carry a real pin**; the other 58 are pin 255, which is the sentinel for
"wakeup-capable but not MPM-routed". The numbers are **hwirq**, not SPI - `GIC_SPI
n` is hwirq `n+32`:

        pin  2 -> hwirq 216  (GIC_SPI 184)   thermal sensor
        pin 47 -> hwirq 165  (GIC_SPI 133)
        pin 50 -> hwirq 172  (GIC_SPI 140)
        pin 53 -> hwirq 104  (GIC_SPI  72)
        pin 62 -> hwirq 222  (GIC_SPI 190)   SPMI arbiter -> PM8941 -> power key

  **Those are hwirq numbers, and this binding wants GIC SPI numbers** - an
  earlier version of this note said they dropped straight in, which was wrong and
  would have silently cost the wakeup. Downstream's own driver compares against
  `irq_data->hwirq`, and its source says so (`mpm-of.c`: "a tuple mapping hwirq to
  a MPM"), while mainline's driver feeds the value into a GIC fwspec as
  `param[1]` with `param[0] = 0` - a **SPI** number. So every entry loses 32:

        qcom,mpm-pin-map = <2 184>, <47 133>, <50 140>, <53 72>, <62 190>;

  Confirmed two independent ways: the dtsi gives `tsens` as `GIC_SPI 184` and
  `spmi` as `GIC_SPI 190`, and the running kernel reports those same two devices
  on hwirq **216** and **222** - exactly 32 apart.

  **That numbering is confirmed two ways rather than assumed.** `spmi@fc4cf000` is
  `GIC_SPI 190` in mainline's dtsi, which is hwirq 222; and the live kernel's own
  wakeup-enabled GIC interrupts are hwirq **222** and **216** - precisely two of
  the five MPM-routed pins. So the power button, which arrives through the PMIC on
  the SPMI arbiter, **is** MPM-routed, on pin 62. A collapsed SoC can be woken.

  There are also 39 GPIO entries (`qcom,gpio-map`, pins 3-41 -> TLMM 102, 1, 5,
  9, ...). Mainline handles GPIO wakeups differently, through
  `wakeup-parent = <&mpm>` on the TLMM plus a `wakeirq_map` in the pinctrl driver,
  which msm8974's pinctrl does not have. Not needed for a first suspend, since the
  power key comes in over SPMI.

*What is left for a first suspend,* in order:

  1. An MPM DT node - `compatible = "qcom,mpm"`, the vMPM `reg`, `mboxes =
     <&apcs 1>`, `interrupts = <GIC_SPI 171 IRQ_TYPE_EDGE_RISING>` (downstream's
     `<0 0xab 1>`), the pin map above, and `qcom,mpm-pin-count` - the count still
     needs confirming, likely 64, which gives `reg_stride` 2.
  2. `CONFIG_QCOM_MPM=y`.
  3. **A hook to flush vMPM at suspend.** `mpm_pd_power_off()` does it, but it is
     registered as a genpd `power_off`, and with no genpd-based cpuidle here
     nothing calls it. Either attach a consumer to that domain or add a small
     exported entry point.
  4. `platform_suspend_ops` driving PC, plus GIC save/restore across the collapse.
  5. RPM sleep votes, which is what turns a collapsed SoC into saved milliamps.

  The vMPM `reg` form still needs checking against how newer DTs express it - on
  those SoCs it is a slice of `qcom,rpm-msg-ram`, and `0xfc4281d0` looks like
  exactly that (`fc428000 + 0x1d0`).

**BLOCKER found 2026-10-01: there is no wakeup path for a collapsed APSS.**
This is the prerequisite the scoping below missed, and it has to be solved before
`platform_suspend_ops` is worth writing at all - without it, a suspend that
collapses the SoC is a phone that **never wakes**.

The existing per-core SPC path works because other cores stay online and the GIC
distributor stays powered. During suspend the PM core parks the secondaries, so
collapsing CPU0 with `L2_OFF` takes the GIC down with it, and nothing is left
watching for a wakeup. That job belongs to the MPM - the always-on block that
holds the wakeup set while the APSS is down - and **mainline has no MPM for this
SoC**:

        MPM node in qcom-msm8974.dtsi   none
        CONFIG_QCOM_MPM                 not set

Worse, the driver mainline does have is a different generation:

        mainline    IRQCHIP_MATCH("qcom,mpm", ...)
                    expects qcom,mpm-pin-count and qcom,mpm-pin-map
        8974        compatible = "qcom,mpm-v2"     (qcom,mpm@fc4281d0)
                    reg = vmpm 0xfc4281d0, ipc 0xf9011008
                    qcom,gic-map  (504 bytes)   qcom,gpio-map (312 bytes)

So it is not a matter of adding a DT node. It needs the downstream mapping
translated into mainline's binding (roughly 63 GIC entries and 39 GPIO entries),
and the driver's assumptions checked against 8974's `vmpm` + `ipc` layout rather
than the RPM-message-RAM layout it was written for. GIC state save/restore across
the collapse is a further piece downstream carries and mainline does not.

**Revised assessment.** Deep suspend is not "the L2 data plus 150-200 lines". It
is: the L2 SAW (**done**, `0072`), an **MPM irqchip port**, `platform_suspend_ops`,
GIC save/restore, and RPM sleep votes. That is a subsystem port, not a patch, and
the MPM is the gate.

**One untested idea worth recording rather than acting on.** The L2 SPM has a
**retention** sequence as well as pc, and retention does not power the block
down - so a suspend path that drove the L2 to RET instead of PC might keep the
GIC alive and still save something, with no MPM needed. Whether RET is enough for
the RPM to apply its sleep set is unknown and probably not, since the RPM keys
off the APSS reaching a sleep state. It would be a cheap experiment once there is
any suspend hook at all, and it is the only route here that does not start with
the MPM.

**Step 1 landed 2026-09-30 (`0072`): the L2 SAW is programmed.** `f9012000` now
binds alongside the four CPU SAWs -

        f9012000.power-manager   <- new
        f9089000.power-manager  f9099000.power-manager
        f90a9000.power-manager  f90b9000.power-manager

and nothing regressed: cpuidle still collects WFI and cpu-spc residency, cpufreq
still ramps all four cores to 960 MHz under load and settles back to 300 MHz, no
oopses. `CONFIG_QCOM_SPM=y`, so it needed a flash; r120 is
`1a3b95afe7cdd8c795bed60c3219c819`.

The patch carries a separate `spm_reg_offset_v2_1_l2` table rather than
extending `spm_reg_offset_v2_1`, because the shared one is missing PMIC_DATA and
adding it there would start writing zeroes over the CPU SAWs' pmic data, which
downstream never does. The offsets (0x40/0x44) are confirmed from downstream's
own `spm-v2.c` register map, whose `VERSION 0xFD0` cross-checks against the DT's
`qcom,saw2-ver-reg`.

**It is not quite inert, and that is worth being precise about.** It adds no new
caller, but `spm.c`'s probe finishes with
`spm_set_low_power_mode(drv, PM_SLEEP_MODE_STBY)`, and the L2 has no standby
sequence - so that resolves to index 0, the **retention** sequence, with
`SPM_CTL_EN` set. The L2 SAW is therefore now armed where Linux previously left
it alone. That matches the shipped state rather than inventing one: downstream's
L2 node carries `qcom,saw2-spm-ctl = 0x00000001`, which is the enable bit with
index 0.

**Scoped 2026-09-30: the SPM data is in hand, and TrustZone does the hard part.**
No code yet, but the shape of the job is now known and it is smaller than
"implement suspend from scratch".

*The enabling discovery.* The per-core idle path already collapses a CPU through
firmware, not through anything Linux programs:

        static int qcom_pm_collapse(unsigned long int unused)
        {
                qcom_scm_cpu_power_down(QCOM_SCM_CPU_PWR_DOWN_L2_ON);

and the flag for the other case **already exists and is exported**:

        #define QCOM_SCM_CPU_PWR_DOWN_L2_ON   0x0
        #define QCOM_SCM_CPU_PWR_DOWN_L2_OFF  0x1
        void qcom_scm_cpu_power_down(u32 flags);   /* EXPORT_SYMBOL_GPL */

So the cluster collapse itself is a TrustZone call we can already make, and the
warm-boot resume path is already set up and proven - `cpuidle-qcom-spm.c` calls
`qcom_scm_set_warm_boot_addr(cpu_resume_arm)` at probe and the per-core SPC path
round-trips through it thousands of times per boot.

*What the SPM driver does and does not do.* `spm.c`'s probe only **initialises** a
SAW - writes the sequences, cfg, delays and pmic data, then selects STBY.
`spm_set_low_power_mode()` is the only mode switch and its one in-tree caller is
`cpuidle-qcom-spm.c`, which is strictly **per-CPU** (it finds each CPU's SAW via
`qcom,saw` on the cpu node). So adding an L2 entry programs the cluster SAW and
**nothing would ever drive it to PC**. On the ARM64 SoCs that do have L2 entries
(8976, 8998, sdm660) PSCI firmware does that driving; `ARM_PSCI` is off here.
There is no prior art to copy either: `arch/arm/mach-qcom/pm.c` has **never**
existed upstream (checked v4.19 through v6.1 - only Kconfig, Makefile,
platsmp.c), and nothing in qcom code registers `suspend_set_ops`.

*The data, extracted from the LineageOS DTB with `tools/romdtb.py`.* Downstream
describes every SAW, and the extraction is **validated**: mainline's existing
8974 CPU entry turns out to be downstream's `wfi` and `spc` sequences
concatenated, byte for byte, with `start_index` on the boundaries -

        downstream wfi (3B)  03 0b 0f
        downstream spc (18B)          00 20 80 10 e8 5b 03 3b e8 5b 82 10 0b 30 06 26 30 0f
        mainline .seq (21B)  03 0B 0F 00 20 80 10 E8 5B 03 3B E8 5B 82 10 0B 30 06 26 30 0F
                             ^STBY=0  ^SPC=3

  **L2 SAW, `qcom,spm@f9012000`** (mainline's `saw_l2` at the same address):

        saw2-cfg        0x00000014      saw2-spm-ctl  0x00000001
        saw2-spm-dly    0x3c102800      core-id       0x0000ffff
        pmic-data0      0x02030080      pmic-data1    0x00030000
        L2-spm-is-apcs-master           (boolean)
        cmd-ret   (5B)  1f 00 03 00 0f
        cmd-gdhs (10B)  00 32 42 03 44 50 02 32 50 0f
        cmd-pc   (16B)  00 10 32 b0 11 42 07 01 b0 12 44 50 02 32 50 0f

  **CPU SAWs** (f9089000/f9099000/f90a9000/f90b9000, cfg 0x1, dly 0x3c102800):

        cmd-wfi   (3B)  03 0b 0f
        cmd-spc  (18B)  00 20 80 10 e8 5b 03 3b e8 5b 82 10 0b 30 06 26 30 0f
        cmd-pc   (18B)  00 20 80 10 e8 5b 07 3b e8 5b 82 10 0b 30 06 26 30 0f
        cmd-ret  (13B)  42 1b 00 d8 5b 03 d8 5b 0b 00 42 1b 0f

  Note **CPU pc differs from spc in exactly one byte** - `0x03` becomes `0x07` at
  offset 6 - so "also drop L2" is a single flag in the sequence. That is a useful
  sanity check on any hand-derived table.

*So the L2 entry writes itself*, following the same concatenation convention
(`MAX_SEQ_DATA` is 64, so 21 bytes is fine):

        static const struct spm_reg_data spm_reg_8974_8084_l2 = {
                .reg_offset = spm_reg_offset_v2_1,   /* see caveat below */
                .spm_cfg = 0x14,
                .spm_dly = 0x3c102800,
                .pmic_data[0] = 0x02030080,
                .pmic_data[1] = 0x00030000,
                .seq = { 0x1f, 0x00, 0x03, 0x00, 0x0f,
                         0x00, 0x10, 0x32, 0xb0, 0x11, 0x42, 0x07, 0x01,
                         0xb0, 0x12, 0x44, 0x50, 0x02, 0x32, 0x50, 0x0f },
                .start_index[PM_SLEEP_MODE_RET] = 0,
                .start_index[PM_SLEEP_MODE_PC]  = 5,
        };

  and the CPU entry needs `start_index[PM_SLEEP_MODE_PC]` plus the 18-byte pc
  block appended to its `seq` (giving 39 bytes, PC at index 21).

*Four things to resolve before writing code.*

  1. **`spm_reg_offset_v2_1` has no `PMIC_DATA_0/1` offsets** - only CFG,
     SPM_CTL, DLY and SEQ_ENTRY. The L2 node carries pmic data, so those writes
     would land at offset 0. `v2_3` puts them at 0x40/0x44; whether the v2.1 L2
     SAW agrees needs checking against the hardware or downstream's
     `spm-devices.c` before trusting it.
  2. **Nothing drives PC.** This is the actual work: a small
     `platform_suspend_ops` whose `.enter` sets the CPU and L2 SAWs to PC and
     calls `cpu_suspend(0, ...)` with a collapse function passing
     `QCOM_SCM_CPU_PWR_DOWN_L2_OFF`. Suspend is the easy case - the PM core has
     already parked the secondaries, so there is no last-man-standing race to
     solve, unlike runtime cluster idle.
  3. **`spm_set_low_power_mode()` is not exported** and the L2's
     `spm_driver_data` is private to `spm.c`, so a suspend path needs a small
     accessor (by phandle, or a registration hook).
  4. **RPM sleep votes are still needed** for the rails to actually drop once the
     SoC does collapse - that is the piece that turns a collapsed SoC into saved
     milliamps, and it remains unwritten (`qcom_smd-regulator.c` votes only
     `QCOM_SMD_RPM_ACTIVE_STATE`).

**The DSPs are not where the power goes - measured 2026-09-19.** Before
committing to the suspend work it was worth asking what the idle draw actually
consists of, since both the ADSP and WCNSS are held up continuously and the ADSP
is only up because the sensor and audio work put it there. USB unplugged, screen
off, `in_current1_raw` sampled every 10s, 24 samples per phase:

| phase | current | delta |
|---|---|---|
| settle | -253.6 mA | |
| A, both DSPs running | **-245.9 mA** | baseline |
| B, ADSP stopped | **-245.2 mA** | **-0.7 mA** |
| C, ADSP + WCNSS stopped | **-213.9 mA** | **-31.3 mA** |

Sample-to-sample spread is about +-30 mA, so with n=24 the ADSP's 0.7 mA is
indistinguishable from nothing and WCNSS's 31 mA is real. The 245.9 mA baseline
also lands on the previously documented 248 mA idle-screen-off figure, which is
a useful independent check that the rig is measuring what it claims.

Two conclusions. **Holding the ADSP up is free**, so the sensors and the audio
transport cost nothing at idle and there is no reason to tear them down for
power. **WCNSS costs about 31 mA**, 13% of idle - real, but it is WiFi being up
rather than a bug, and worth remembering that power save is deliberately off
(see [[xperia-z1c-wifi-fix]]), which may be part of that.

**And the headline: with both DSPs stopped, 214 mA remains.** That is 87% of the
idle draw untouched, so there is no cheap win hiding in the peripherals - the
draw really is the SoC never collapsing, exactly as the analysis below argues.
It does mean the deep-suspend prize is now quantified rather than assumed.

**A correction to the plan below.** Sleep-set votes are described further down as
"the cheapest first experiment by a wide margin". They are cheap to write and
**impossible to validate**: the RPM applies the sleep set only when the APSS
signals it has entered sleep, and nothing here ever does. `spm.c`'s
`spm_match_table` carries `qcom,msm8974-saw2-v2.1-cpu` but **no `-l2` entry**, so
the `saw_l2` node the DT describes at `f9012000` is never programmed, and
cpuidle offers only per-core `cpu-spc`. Other SoCs in that table (8976, 8998,
sdm660) do have L2 variants with their own `spm_reg_data`; msm8974 does not.
So the votes would never fire, and doing this properly means the L2 SPM data,
something to drive cluster-level idle, and `platform_suspend_ops` - and
`arch/arm/mach-qcom` no longer has a `pm.c` at all.

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

   **Settled, and it is (2) - with a much bigger consequence than interrupts.**
   Nine registers under `0x100` have non-zero power-on values. Every one of them
   reads `0x00`:

        addr   read   POR
        0x019  0x00   0x08    HDRIVE_OVERRIDE
        0x020  0x00   0x44    ANA_CSR_WAIT_STATE
        0x040  0x00   0x80    PROCESS_MONITOR_CTL0
        0x043  0x00   0x01    PROCESS_MONITOR_CTL3
        0x094  0x00   0xff    INTR_MASK0
        0x095  0x00   0xff    INTR_MASK1
        0x096  0x00   0x3f    INTR_MASK2
        0x097  0x00   0x3f    INTR_MASK3

   The same addresses read `0x00` through the interface device's map too. Yet the
   codec is plainly alive and addressable higher up: `0x1ab` reads `0xb0` while a
   tone plays and `0x80` at idle, tracking the headphone PA enable bit exactly.
   **So the whole register block below `0x100` is unreachable, and everything at
   or above it works.**

   ### Why that matters far more than the interrupt

        #define WCD9XXX_A_CDC_CTL      (0x80)
        #define WCD9XXX_A_LEAKAGE_CTL  (0x88)

   Both are inside the dead block. `wcd9320_bring_up()` brings the codec's
   digital core out of reset by toggling `A_CDC_CTL` 0 then 3 - **and those
   writes have been going nowhere all along.** The digital core is never enabled.
   That accounts for the whole picture at once: no interrupts can be generated,
   `INTR_*` cannot be configured, the SLIMbus channel-close handshake never
   completes, and playback runs end to end in silence while every layer above
   reports success. `regmap_write()` returning 0 means the SLIMbus write was
   accepted, not that it landed anywhere.

   **SOLVED by `0059`: every register is at `0x800 + N`.** `wcd9xxx-core.c`
   downstream adds `WCD9XXX_REGISTER_START_OFFSET`, which is `0x800`, to the
   value-element offset in both its read and write helpers:

        msg.start_offset = WCD9XXX_REGISTER_START_OFFSET + reg;

   This driver passed raw register numbers to `regmap_init_slimbus()`, so every
   access landed `0x800` low. `regmap_config` has a field for exactly this -
   `reg_base`, applied in `regmap_reg_addr()` when the bus transfer is formatted,
   so `max_register` and the readable/volatile callbacks keep using the driver's
   own numbering. Adding `.reg_base = WCD9320_REGISTER_START_OFFSET` to both the
   codec and interface maps is the whole fix.

   `wcd9335` does not need it because its register constants already carry the
   page - `0xB56` and friends - which is why a plain `regmap_init_slimbus()`
   works there and hid the problem here.

   **What changed on the hardware.** The block below `0x100` now reads real
   values instead of zeros:

        019: 09   020: 44   040: 80   043: 01
        094: fe   095: ff   096: 3f   097: 7f

   `0x020`, `0x040`, `0x043`, `0x095` and `0x096` match their power-on values
   exactly, and `0x094` reads `0xfe` - which is precisely what `0056` writes to
   unmask the SLIMbus source, so driver writes are landing too. **`A_CDC_CTL` is
   `0x80`, so the codec's digital core is being brought out of reset for the
   first time.**

   And the interrupt works: `msmgpio 72` went from **0 to 888**, the handler
   decodes **786 SLIMbus port interrupts** during a playback, and there are no
   errors anywhere on the path.

   ### What is left

   The channel-close handshake still times out, and now for a simple reason:
   `wcd9320_slimbus_irq()` - the function that clears `ch_mask` and wakes
   `dai_wait` - is still never registered. The slim-side `irq_handler()` receives
   the port interrupts and clears the port status, but nothing clears `ch_mask`.
   Wiring those together is the next job, and it is now a small one.

   **SOLVED by `0060`: the port interrupt now reaches the codec half, and the
   close handshake completes.** The two halves are separate drivers over one piece
   of silicon, and only the slim half owns the interrupt line, so there was no way
   for a port interrupt to reach the code that knows about DAIs: `struct wcd9320`
   held no pointer to `struct wcd9320_priv`. The link goes in the one structure
   both halves already share, `struct wcd_slim_data` - a `codec_priv` field the
   component probe publishes with `smp_store_release()` *after* it has
   `init_waitqueue_head()`'d every `dai_wait`, and retracts on remove. The slim
   handler then loads it with `smp_load_acquire()` and calls
   `wcd9320_slimbus_irq()`.

   **It replaces the slim side's own port decode rather than running after it.**
   That ordering is the whole point: the codec handler repeats the same four
   status reads, and reading them first would have handed it four zeroed registers
   and left the handshake timing out exactly as before. The slim side's inline
   decode is what produced the 786 decoded port interrupts under `0059`, and it
   was still useless, because clearing port status is not what
   `wcd9320_codec_enable_slim_chmask()` waits on - `dai->ch_mask` is.

   **Measured, three consecutive runs on r101:** `Slim close tx/rx wait timeout`
   does not appear once, where before it appeared on every playback. One interrupt
   per run, no storm, no `Couldn't find slimbus ... port` warnings.

   **`0060` also sweeps up the acknowledge.** The codec handler has an early
   `continue` for a port whose interrupt is not enabled, and that path skips the
   per-port `INT_CLR` write at the bottom of its own loop. The line is level
   triggered, so a status bit nobody acknowledged holds it asserted and it re-fires
   without end - the same storm `IRQF_TRIGGER_LOW` produced on its own before the
   status registers were being cleared properly (4427 interrupts, all registers
   reading zero). The slim half now re-reads the four status registers after the
   call and clears whatever is left, which is what it used to do unconditionally.
   This has not been observed to trigger; it is there so the door stays shut.

   **Still not audible, and there is a concrete next lead: overflow.** Every
   playback logs

        wcd9320_slimbus_irq: overflow error on RX port 1, value 5
        wcd9320_slimbus_irq: overflow error on RX port 2, value 5

   `value 5` is `OVERFLOW | PORT_CLOSED`. An overflow on an *RX* port means data is
   arriving that the codec is not consuming, which is what silence would look like
   from the bus's side, so this is worth chasing before anything else.

   **And overflow can still swallow a close, in one specific case.** The handler
   *disables* a port's interrupt on overflow, the way downstream does, to stop an
   overflow storm. When both bits arrive in the same interrupt (`value 5`) the
   close is handled in the same pass and nothing is lost. But on the very first
   playback after `modprobe`, before the routing above is applied, overflow arrives
   *alone* (`value 1`) in an earlier interrupt, masks the port, and the later
   port-closed event then has no enabled interrupt to arrive on - which is the one
   remaining `close tx/rx wait timeout` in the boot log, at 69.6 s. Fixing the
   overflow should make this moot; if it does not, the mask needs to be narrowed so
   it cannot cost a close.

   **Whether that alone restores audio is not proven.** The SLIMbus data path is
   hardware and interrupts are status reporting, so it is possible sound needs
   something further. But it is the one concrete unimplemented subsystem left on
   the path, and the close timeout is direct evidence it matters.

   **It did not restore audio, and the remaining fault is now pinned down
   precisely.** During playback the SLIMbus RX ports sit in *permanent*,
   continuously-asserted overflow. The probe that establishes this, and its
   control, matter more than the conclusion:

        (stream running)  write INT_CLR_RX_0 = 0xff
                          read  INT_STATUS_RX_0  ->  0x06   immediately
        (no stream)       write INT_CLR_RX_0 = 0xff
                          read  INT_STATUS_RX_0  ->  0x00   and stays 0x00

   The clear works; the condition just re-asserts inside a single register read.
   So the codec is not draining slowly or drifting out of sync - it consumes
   **nothing at all**, from the first sample. And since a sink can only overflow
   if something is filling it, the SLIMbus transport and the ADSP side are both
   working. That is the useful half of this finding: everything up to and
   including delivery into the codec is correct, and the fault is entirely
   inside the codec's own consumption of the port.

   **Live register writes now work on this build**, which is what made the rest
   of this possible - `9000-debug-regmap-allow-write-debugfs.patch` is in the
   recipe, so both codec regmaps take writes:

        /sys/kernel/debug/regmap/217:a0:1:0/registers   PGD, the codec proper
        /sys/kernel/debug/regmap/217:a0:0:0/registers   IFD, the SLIM ports

        echo "3ae 28" | sudo tee /sys/kernel/debug/regmap/217:a0:1:0/registers

   Prefer this over another build for anything register-shaped.

   **Ruled out by live experiment - each one poked to its downstream value mid
   playback, each one no change whatsoever:**

   - *Class-H, buck, NCP and the charge pump.* The whole downstream HPH enable
     sequence was replayed by hand (`CLK_OTHR_CTL`=0x01, `BUCK_MODE_1`=0xa5 with
     bit 7 set, `NCP_EN`=0xff, `CLSH_B1_CTL`=0xa7, plus both param tables).
     Overflow identical before and after. This was the leading hypothesis -
     `0054` disables Class-H and the rails really are off at POR - and it is
     **wrong**. Worth knowing before anyone spends a day porting `wcd-clsh.c`:
     it is still the right thing to do for power and probably for audibility,
     but it is not what is stopping the data.
   - *SLIM RX port sample width.* Both as a live poke and, in `0061`, as a
     proper fix in its correct place before the stream opens.
   - *Mixer input routing.* The data lands on slave ports 17 and 18, which are
     internal mixer inputs **RX2 and RX3**, not RX1/RX2 - `rx_mix1_inp =
     ch->port + RX_MIX1_INP_SEL_RX1 - 16` and `RX_MIX1_INP_SEL_RX1` is 5. So the
     routing recipe further up aims `RX1 MIX1 INP1` at a port carrying nothing.
     Pointing the mixers at the ports that do carry data (`CONN_RX1_B1_CTL`=0x06,
     `CONN_RX2_B1_CTL`=0x07) changes nothing about the overflow either, but the
     recipe is still wrong and that is worth remembering when reading old logs -
     it explains the lone `AIF_PB DAI(0) connected to RX2` line.

   **Verified correct, so do not re-check these:**

   - Stream config, read straight out of `slim_stream_prepare` with a kprobe:
     `rate=48000 bps=16 chc=2 pm=0x60000 dir=0`. `dir=0` is playback, which is
     what makes the core send CONNECT_SINK.
   - Interpolator rate: `RX1/RX2_B5_CTL` bits 7:5 = 0x60 = 48 kHz. The port
     writes `comp_fs << 5` where downstream passes a separate `rx_fs_rate`, but
     the two tables line up at **every** rate (8k/16k/32k/48k/96k/192k ->
     0x00/0x20/0x40/0x60/0x80/0xA0), so the conflation is harmless.
   - Port config `0x41`/`0x42` = 0x05 = `WATER_MARK_12BYTES | SLAVE_PORT_ENABLE`,
     and the channel map `0x184`/`0x188` = 0x06. Both match downstream, which
     computes that payload over the whole channel list and writes it to every
     port in the group.
   - `A_CDC_CTL`=0x03, `CLK_RX_B1_CTL`=0x03, `CLK_MCLK_CTL`=0x01, and every DAPM
     widget from `AIF1 PB` through `SLIM RX1/2`, the mixers, interpolators,
     `RX1/2 CHAIN`, the DACs and `HEADPHONE` reads `On`.

   **`0062` fixes one more real divergence, and does not fix the overflow.**
   Downstream activates the SLIMbus channel from the SLIM RX widget's
   `SND_SOC_DAPM_POST_PMU`, as the last thing `taiko_codec_enable_slimrx()` does.
   This port called `slim_stream_enable()` from the DAI's `prepare` callback
   instead, and ALSA runs `hw_params` -> DAI `prepare` -> and only then does
   `soc_pcm_prepare()` raise `SND_SOC_DAPM_STREAM_START`. So the ADSP began
   filling the slave port while the codec's RX chain was still powered down.
   That looked like an exact explanation for a port that overflows from the
   first sample. **It is not:** with the ordering corrected the overflow is
   unchanged, measured with the PCM confirmed `RUNNING` throughout. What it does
   fix is the last surviving close timeout - the one on the first playback after
   `modprobe`, which `0060` could not reach because the overflow arrived alone
   and masked the port before the close. Total close timeouts since boot is now
   **0**.

   **A trap worth naming, because it produced a wrong answer for several
   minutes.** A clean overflow status and a stopped stream look *identical* -
   both read `INT_STATUS_RX_0 = 0x00`. One run of the probe appeared to show the
   overflow clearing after `0062` and it was briefly believed to be the fix; it
   was not reproducible, and re-running with `pgrep speaker-test` and
   `/proc/asound/card0/pcm0p/sub0/status` asserted alongside every reading showed
   `state: RUNNING` with `0x06` on every probe. Any overflow probe must carry a
   liveness check, the same way the proximity work needed a control sensor.

   **`0063` removes a real off-by-one that had the driver reading a port nobody
   fed.** Downstream's port enum starts at `TAIKO_RX1 = 0` and there is no
   `TAIKO_RX0`; this port invented one, which shifted every RX index up by one.
   `"SLIM RX1 MUX"` carries its index in the widget's shift field and
   `slim_rx_mux_put()` uses it to pick `rx_chs[]`, so the mux named RX1 was
   subscribing `rx_chs[1]` - slave port **17** - while the mixer in front of it
   wrote `RX_MIX1_INP_SEL_RX1` for the enum text "RX1", and that value selects
   slave port **16**. The DAPM route `{"RX1 MIX1 INP1", "RX1", "SLIM RX1"}`
   asserts those are the same port; they were not. With the enum renumbered the
   channel map moves from 145/146 to 144/145 and the overflow moves from ports
   1/2 to ports 0/1, which is the shift made visible.

   **It is still not the cause.** With everything self-consistent for the first
   time - mixer reading port 16, data arriving on port 16, whole path powered,
   `1ab=a0 1b1=c0` - the port overflows exactly as before, `status=0x03` on every
   probe with the PCM confirmed `RUNNING`. Keep the patch: it is correct, it
   matches downstream, and a future session should not have to find it again.

   **Also worth knowing: the DAPM route table is incomplete.** Only the identity
   routes exist -

        {"RX1 MIX1 INP1", "RX1", "SLIM RX1"},
        {"RX2 MIX1 INP1", "RX2", "SLIM RX2"},

   so selecting any other input, such as `RX1 MIX1 INP1 = RX2`, connects to
   nothing and the entire chain stays powered down - `1ab=80 1b1=40`, no widgets
   on. That is a silent failure mode: the routing commands all succeed, `amixer`
   reports the new value, and the only symptom is that nothing powers up.
   Downstream carries the full cross-connect. Anyone testing alternative routing
   must check the DAPM power state, not just the control value.

   **`0061` and `0063` interact, and the net answer is `0x0a`.** `0061` argued
   the sample-width register should be `0x28` because a stereo stream lands on SB
   ports 1 and 2. That was true *under the broken numbering*. With `0063` the
   stream lands on SB ports 0 and 1, so the correct value is
   `(0x2 << 0) | (0x2 << 2)` = **`0x0a`** - which is exactly what the old
   hardcoded write produced. The hardcoded value was right by accident and the
   enum was the thing that was wrong. `0061` is still worth keeping, because it
   derives the field per channel instead of assuming stereo, but its commit
   message names a value that no longer applies. The register reads `0x3ae =
   0x0a` on the phone now, which is correct.

   **Four more things ruled out, with the ordering objection answered.** A fair
   criticism of the earlier live pokes is that they were all applied *after* the
   overflow had already latched, so a negative proved nothing. That objection has
   now been tested and does not save any of them:

   - *Class-H and the rails, set before the stream starts.* Written while idle
     (`CLK_OTHR_CTL`=0x01, `BUCK_MODE_1`=0xa5, `NCP_EN`=0xff), confirmed still
     set during playback, overflow unchanged. This is the properly-ordered
     version of the earlier test and it agrees.
   - *The port is not latched.* Bouncing the slave port's enable bit
     (`PORT_CFG` 0x05 -> 0x04 -> 0x05) with the RX chain already up and clearing
     the status while disabled does not make it drain. So the port is not stuck
     in an error state from the early overflow; it is simply never read.
   - *Every value downstream sets is already set.* All four downstream tables
     (`taiko_reg_defaults`, `taiko_1_0_`, `taiko_2_0_`, `taiko_codec_reg_init_val`)
     were parsed, mapped onto our register names and diffed against a live dump
     taken during playback: **zero mismatches**. The missing piece is not a
     register value.
   - *The write order is now captured.* The `regmap:regmap_reg_write` tracepoint
     works, so a whole playback can be recorded:

        echo 1 > /sys/kernel/tracing/events/regmap/regmap_reg_write/enable

     An entire playback is only 27 writes to the PGD and 11 to the interface
     device. Note the trace shows *changes* only - regmap skips writes that match
     the cache - so an absent register is not necessarily an unwritten one.

   **What the trace does show** is the interface device being configured and
   enabled (`0x180`/`0x40`, `0x184`/`0x41`) early, the overflow handler masking
   both ports (`INT_EN0` -> `0xfc`) within milliseconds, and only *then* the RX
   chain coming up - reset pulse at `0x301`, interpolator clock at `0x30f`, DAC,
   PA. That ordering is inherent to DAPM, which powers source-to-sink, and
   downstream has the same shape, so it is expected rather than wrong. What is
   wrong is that the port never recovers once the interpolator does start.

   **The codec is being fed the wrong master clock, and that is almost certainly
   why nothing drains.** Every register on the path is right because register
   access rides the SLIMbus clock and does not need MCLK at all - which is
   exactly why months of register comparison found nothing. Measured on the
   phone:

        /sys/kernel/debug/clk/div_clk1/clk_rate          19200000
        qcom,codec-clk-rate (DT)                          9600000
        A_CHIP_CTL 0x06                                       0x02  = 9.6MHz

   `wcd9320_parse_dt()` calls `clk_set_rate(clk, 9600000)` and **ignores the
   return value**. A kretprobe shows the call returns **0, success**, while the
   rate never changes. The reason is in mainline:

        DEFINE_CLK_SMD_RPM_XO_BUFFER(div_clk1, 11, 19200000);

        static const struct clk_ops clk_smd_rpm_branch_ops = {
                .prepare, .unprepare, .recalc_rate      /* no .set_rate */
        };

   With no `.set_rate` and no `.determine_rate`, the clock core decides the rate
   is already correct and returns success without touching anything. So the DT
   comment on the codec node - "9.6MHz, which is CXO/2 and so RPM_SMD_DIV_CLK1" -
   was wrong twice: that clock is CXO itself, 19.2MHz, and it cannot be divided.
   A Taiko accepts **only** 9.6 or 12.288MHz, so it is running at exactly twice
   its configured clock, or not running at all.

   **The intended fix, and why it is not in the tree.** Mainline has the right
   driver for this - `SPMI_PMIC_CLKDIV`, whose help text says "it configures the
   frequency of clkdiv outputs of the PMIC. These clocks are typically wired
   through alternate functions on GPIO pins." That is this board: stock's
   `qcom,cdc-mclk-gpios` is PM8941 GPIO 15. The driver divides the 19.2MHz XO by
   powers of two - 9.6MHz is one step - and unlike the RPM clock it implements
   `.set_rate`. The binding's own example even assigns 9600000.

   The attempt added a `qcom,spmi-clkdiv` node at `0x5b00` under `pm8941_0`,
   pointed the codec's `clocks` at `<&pm8941_clk_divs 1>` with
   `assigned-clock-rates = <9600000>`, muxed GPIO 15 to `function = "func1"`
   through the codec's own `pinctrl-0`, stopped the driver claiming that pin as
   an ordinary GPIO (`gpio_request()` muxes it straight back to "normal", so held
   high it carries DC and not a clock), and set `CONFIG_SPMI_PMIC_CLKDIV=y`.

   **It hung the boot.** The phone did not enumerate on USB at all - not the
   network gadget, not fastboot - so it hangs before USB comes up, which is
   earlier than a failed codec probe would explain. Reverted; the boot image was
   restored from `boot-images/boot-r90.img` over fastboot and the modules rebuilt
   without it. Zero close timeouts afterwards, no regression.

   **If you pick this up, narrow it before flashing again.** The change did five
   things at once and any of them could be the one that hangs. Split them: the
   `CONFIG_SPMI_PMIC_CLKDIV=y` driver alone with no DT node at all is inert and
   safe to boot first; then the clkdiv node alone with nothing consuming it; then
   the pin mux; and only then move the codec's `clocks` over. Which of the three
   CLKDIV peripherals (`0x5b00`, `0x5c00`, `0x5d00`) actually reaches GPIO 15 is
   also unverified - the codec was pointed at the first one on the reasoning that
   CLKDIV1 is the usual audio MCLK, and that is a guess. There is no SPMI regmap
   in debugfs on this build, so the PMIC's clkdiv registers could not be read to
   check; adding one would settle it without a single reboot.

   **Recovery, since it will probably be needed again.** Power off with
   **Power + Volume Up** (a ten-second power hold does nothing on this phone), then
   hold Volume Up while plugging USB - the LED turns blue for fastboot - then
   `fastboot flash boot boot-images/boot-r90.img` and `fastboot reboot`. Note the
   modules in the rootfs may be newer than the restored kernel; `pkgver` is
   `6.16.12` for every build so they still load, but rebuild and reinstall the
   matching package afterwards or the two halves disagree.

   **Correction: that 19.2MHz is not a measurement, and the clock is probably
   fine.** `/sys/kernel/debug/clk/div_clk1/clk_rate` does not read the hardware.
   It echoes a *software constant* - the `19200000` literal inside
   `DEFINE_CLK_SMD_RPM_XO_BUFFER(div_clk1, 11, 19200000)` - through a
   `recalc_rate` that returns it verbatim. It says nothing about the pin. The
   note above presented it as measured fact and that was wrong.

   The downstream evidence now points the other way. Downstream declares the same
   clock the same way, `DEFINE_CLK_RPM_SMD_XO_BUFFER(div_clk1, div_a_clk1,
   DIV_CLK1_ID)`, wires it to the codec as `osr_clk`
   (`CLK_LOOKUP("osr_clk", div_clk1.c, "msm-dai-q6-dev.16384")`), and **never
   calls `clk_set_rate` on it at all** - just `clk_get` and
   `clk_prepare_enable`, exactly like this port. Its codec is told 9.6MHz through
   `A_CHIP_CTL` exactly like ours. If 19.2MHz really reached the pin, downstream
   would be just as broken. The likeliest reading is that RPM or the board
   configuration already divides that buffer to 9.6MHz and **both kernels simply
   mislabel it**. `clk_set_rate()` succeeding without doing anything is still a
   wart worth knowing about, but it is probably harmless.

   **And the PMIC divider is a dead end on this PMIC.** Landing just the driver
   and an inert `qcom,spmi-clkdiv` node at `0x5b00` under `pm8941_0` - nothing
   consuming it, no pin mux, codec untouched - hung the boot exactly as the
   five-part version had, with no USB at all, neither gadget nor fastboot. That
   bisect is the useful part: the hang is the driver reaching that address over
   SPMI, not anything to do with the codec. **PM8941 has no CLKDIV peripheral
   there**; those arrived on later PMICs like the PM8998 in the binding's own
   example, and on 8974 the PMIC clock buffers are managed by RPM instead, which
   is exactly why mainline models them as RPM clocks. Do not retry this. Reverted
   in full; `boot-images/boot-r90.img` restored over fastboot both times.

   **A confound removed: it is not a second, unconsumed port.** Every earlier
   overflow reading was `status_rx0 = 0x03`, both ports 0 and 1, because
   `SLIM RX2 MUX` had been left subscribed by an earlier test while only RX1's
   mixer was ever routed - so port 1 legitimately had no consumer. Clearing every
   `SLIM RX<n> MUX` to `ZERO` first and subscribing only RX1 gives the clean
   case: one channel (`0x180 = 0x01`), one port enabled, mixer on `RX1`
   (`CONN_RX1_B1_CTL = 0x05`), chain powered (`1ab = 0xa0`, `30f = 0x01`) - and
   `status_rx0 = 0x01`. **A single correctly-mapped, correctly-routed port still
   never drains.** Clear the muxes first in any future test; the default state is
   not empty.

   **`CDC_CONN` is missing compared to downstream, and it is not the answer.**
   Downstream has a supply widget this port lacks entirely -
   `SND_SOC_DAPM_SUPPLY("CDC_CONN", WCD9XXX_A_CDC_CLK_OTHR_CTL, 2, 0, ...)` - and
   that register reads `0x00` here, never written. It looked promising because
   the RX mixer inputs are exactly the `CDC_CONN_RX*` registers. Sweeping every
   bit of `A_CDC_CLK_OTHR_CTL` live during playback, up to `0xff` with all bits
   set, changes nothing. Downstream only routes `CDC_CONN` to capture-side
   widgets (the DEC muxes, MAD, I2S) anyway, never to the RX path.

   **The wcd9335 lifecycle does not transplant.** wcd9335 is the only sibling
   that works on mainline's SLIMbus stream API, and it runs **both**
   `slim_stream_prepare()` and `slim_stream_enable()` from `wcd9335_trigger()` on
   `TRIGGER_START`, with teardown on `TRIGGER_STOP`; `hw_params` only computes
   the config, writes the interface device's channel map and watermark, and calls
   `slim_stream_allocate()`. This port called `slim_stream_prepare()` from
   `hw_params` - and that call is not passive, it walks the port mask running
   `slim_connect_port_channel()` - so the port was attached to the channel long
   before the codec chain existed. That is a real divergence and it was worth
   trying. Matching the split exactly, verified live by kretprobe
   (`sprep: (wcd9320_trigger+0x74 <- slim_stream_prepare) ret=0`), **does not fix
   the overflow** and **regresses the close handshake**: the timeout returns on
   every playback, eight in one boot. The reason is that our
   `wcd9320_codec_enable_slim_chmask(dai, false)` wait lives in
   `SND_SOC_DAPM_POST_PMD`, which now runs *after* `trigger(STOP)` has already
   closed the ports, so the wait never sees them close. wcd9335 has no such wait
   at all. Reverted; timeouts back to zero.

   **Also verified equal to wcd9335, so do not re-check:** the interface register
   arithmetic (`RX_PORT_CFG(16+p) = 0x30+16+p = 0x40+p`,
   `RX_PORT_MULTI_CHNL_0(16+p) = 0x140+4*(16+p) = 0x180+4p`), the watermark
   constant (`(12BYTES << 1) | ENABLE` = `0x05`), the port table
   (`{.port = p + 16, .shift = p}`), and `port_mask` (`BIT(ch->port)`, bits 16+).

   **The overflow bit was finally validated, and it means what we assumed.**
   Everything above rests on reading OVERFLOW as "data is arriving and nothing is
   consuming it", and that had never been checked against a negative control.
   With no stream anywhere, disable both ports, clear the status, then enable
   port 0 alone with the same `WATER_MARK_VAL`:

        ports disabled, status=0x00
        port enabled, no stream, t=1s: status=0x00 src0=0x00  clean
                                 t=2s: status=0x00 src0=0x00  clean
                                 t=3s: status=0x00 src0=0x00  clean

   An enabled port with nothing feeding it does **not** report overflow. So the
   bit is not a side effect of enabling a port, and during playback the ADSP
   really is delivering into the port while the codec really is consuming
   nothing. The instrument is sound and the conclusion stands.

   (Note the starting state in that run: `status=0x03` with no stream running at
   all, left latched from the previous playback. Latched status survives the
   stream, so always clear before measuring.)

   **A golden reference is reachable with zero writes, and here is the recipe.**
   The phone already has TWRP installed on `FOTAKernel` (mmcblk0p16) - boot it
   with the volume-down combo, *not* `fastboot boot`, which this Sony bootloader
   does not honour (it hangs at the Sony logo). TWRP runs the **downstream 3.4.0
   vendor kernel**, the one whose WCD9320 driver works. adb comes up as
   `recovery`. Nothing below writes to the device; the mounts are read-only or
   volatile and vanish on reboot:

        mount -o ro /dev/block/mmcblk0p23 /s      # system: LineageOS 18.1
        mkdir -p /firmware/image
        mount --bind /s/system/etc/firmware /firmware/image
        setsid sh -c "exec 3<>/dev/subsys_adsp; sleep 600" &   # boots the ADSP
        mount -t debugfs none /sys/kernel/debug

   The ADSP really does boot this way - `pil-q6v5-lpass ... adsp: Brought out of
   reset` - and then SLIMbus enumerates **both** `taiko-slim-ifd` and
   `taiko-slim-pgd` and `taiko_codec` binds. So the whole downstream stack can be
   stood up in recovery, on this phone, without touching pmOS.

   **What it cannot do, so far: play.** `snd_soc_register_card()` returns
   -EPROBE_DEFER. The very first attempt at boot got further - all the DAI
   mappings succeeded and it then failed with `failed to init SLIMBUS_0_RX: -19`
   0.4s after the ADSP came out of reset, which looks like it simply raced the
   AFE service. After that failure `taiko_codec_remove()` tore the component
   down, and every rebind since defers because the q6 DAI components are gone.
   Unbinding and rebinding `taiko_codec` and the card in various orders does not
   recover it. So there is still no dump of the registers *during* a working
   playback, which is the one that would settle this.

   **And the register window is narrower than hoped.** Downstream's debugfs is
   `/sys/kernel/debug/wcd9310_slimbus_interface_device/{peek,poke}` - write an
   address to `peek`, read the value back - but `codec_debug_write()` routes both
   through `wcd9xxx_interface_reg_read/write`, so it reaches the **interface
   device only**, registers <= 0x3FF. There is no PGD/codec equivalent.

   **The dump we did get says the interface device matches.** Downstream, codec
   bound, no playback, every non-zero interface register:

        001: 0x21   002: 0x01   020: 0x4d   021: 0x47
        030: 0xff   031: 0xff   032: 0xff

   Identical to ours - same `0x21/0x01/0x4d/0x47`, same all-ones interrupt
   enables. The interface device is configured the same way on both sides.

   **The card failure is now pinned down exactly, and it is a race in APR.**
   Turning on ASoC's dynamic debug (`echo "file sound/soc/soc-core.c +p" >
   /sys/kernel/debug/dynamic_debug/control`) before the probe makes it name what
   it is waiting for, instead of deferring silently. The real sequence is:

        [35.691] apr_tal:Q6 Is Up
        [36.004] apr_register: adsp not up
        [36.004] afe_set_config: Q6 interface prepare failed -19
        [36.004] msm_afe_set_config: Failed to set codec registers config -19
        [36.005] msm_audrx_init: Failed to set AFE config -19

   The card's deferred probe retries the instant the ADSP's q6 DAIs register,
   about 300ms after `apr_tal` announces Q6, and APR's own subsystem-state
   notifier has not marked the ADSP loaded yet, so `apr_register` refuses.
   **-19 is not -EPROBE_DEFER, so there is no second automatic attempt.** Win
   that race and the card should come up; everything before it already succeeds,
   including every DAI mapping.

   **Three traps, all learned the hard way:**

   - **Hold the ADSP open from the host**, not the device:
     `adb shell 'exec 3<>/dev/subsys_adsp; while :; do sleep 5; done'` as a
     background job on the laptop. TWRP kills device-side background processes
     when adb disconnects, and dropping that fd runs `subsystem_put()`, which
     shuts the ADSP down and takes all the q6 DAI devices with it.
   - **Do not unbind/rebind `taiko_codec`.** It perturbs the ASoC component list,
     and afterwards the card can no longer resolve `msm-dai-q6-dev.241` - the
     DAI that `qcom,msm-dai-q6-be-afe-pcm-rx.189` registers - even though all 26
     q6 DAI devices are still bound. That state does not recover; only a reboot
     clears it.
   - **Neither `fastboot boot` nor `adb reboot recovery` works** on this
     bootloader. Recovery is only reachable with the key combo, so every attempt
     costs a manual step.

   **That experiment was run on a clean boot, and it fails. The TWRP route is
   closed for a *playing* reference.** Fresh boot, ADSP held from the host, the
   retry failing with -19 exactly as predicted, then binding the card by hand
   without going anywhere near `taiko_codec`:

        msm8974-asoc-taiko fe02b000.sound: CPU DAI msm-dai-q6-dev.241 not registered

   So the earlier guess was wrong: it is **not** caused by rebinding the codec.
   The -19 failure's own cleanup tears down the AFE-PCM RX ASoC DAI, and once
   that is gone no later bind can resolve it. Re-registering just that one device
   does not work either - `unbind`/`bind` on
   `qcom,msm-dai-q6-be-afe-pcm-rx.189` through `msm-dai-q6-dev` both return
   failure, even with the driver path read straight out of sysfs.

   That makes the race structurally unwinnable from userspace. The card gets
   exactly one automatic probe, it fires the instant the q6 DAIs register, and
   APR is not ready for another ~300ms; the failure then destroys the DAI that a
   retry would need. Fixing it means delaying the probe or making `afe_set_config`
   retry - a kernel change, and TWRP's kernel is a prebuilt blob. Everything up
   to that point still works and the recipe above is still the cheapest way to
   stand up the downstream stack for *non-playing* inspection.

   **Operational trap, learned the hard way:** after TWRP has run downstream's
   ADSP firmware, the **next pmOS boot fails SLIMbus enumeration** -

        QMI TXN wait fail: -110
        slim resource not idle: -110
        wcd9320-slim 217:a0:0:0: Failed to get logical address
        wcd9320-slim 217:a0:1:0: Failed to get logical address

   - and no card appears even though the module loads. The ADSP is left in a
   state pmOS's remoteproc cannot re-initialise. **One more reboot clears it**
   and everything comes back normally. Do not go debugging that; just reboot
   again.

   **Failing that**, the expensive route is a real LineageOS boot, which formats
   userdata and so destroys pmOS; **take a fresh backup first**, because the one
   in `backups/` is from 2026-09-09 and predates all of this.

   **A golden reference now exists**, in `docs/golden-reference/`, captured from
   LineageOS 18.1 on this phone with audio actually playing. Read that directory's
   README before doing anything else here - it is the only picture we have of
   this codec working, and it cost the pmOS install to get. The headline results:
   downstream's SLIMbus ports **never overflow** and its interface device is
   byte-identical idle and playing; its per-port status byte reads **0x20** where
   ours reads **0x42**; and every *digital* register we set already matches, so
   the fault is not a codec register value.

   **Restoring pmOS afterwards is documented in `backups/RESTORE.md`** and is
   worth reading before you need it: TWRP's toybox breaks silently past 2 GiB in
   both `dd` and `cat`, `adb push` is the only workable write path and it skips
   the final sector, and a not-quite-perfect inner GPT leaves pmOS stuck in the
   initramfs with `failed to mount subpartitions` and only telnet on port 23 to
   get in with.

   **Two of those three leads are now dead, measured on the phone.**

   *The SLIMbus transactions all succeed.* Tracing `slim_do_transfer` across a
   whole playback: 49x `mc=104` (value-element messaging), 24x `mc=96`, 2x
   `mc=17` - that is **CONNECT_SINK, once per port** - and 2x `mc=20`
   (DISCONNECT_PORT) on teardown. **Every single one returns 0.** So the
   discarded return value in `slim_stream_prepare()` is a real wart in mainline,
   but it is not hiding a failure here.

   *The absence of DEFINE/ACTIVATE_CHANNEL is expected, not a bug.* There is no
   `mc=0x50`/`0x54` in the trace because `slim_stream_enable()` short-circuits:

        if (ctrl->enable_stream) { ret = ctrl->enable_stream(stream); ... return ret; }

   and the NGD controller sets `ctrl->enable_stream =
   qcom_slim_ngd_enable_stream`, which packs the whole thing into one
   `SLIM_USR_MC_DEF_ACT_CHAN` message to the ADSP instead. The rate maths inside
   it is right: `rootfreq = 24576000>>3 = 3072000`, `superfreq = 3072000/768 =
   **4000**`, so `ratem = 48000/4000 = 12`, giving coef 3 and exp 2 - CRM
   `3*2^2 = 12`. Correct.

   *And the ADSP is told exactly the right thing.* kprobe on
   `q6afe_slim_port_prepare`:

        rate=48000 bw=16 fmt=0 nch=2 ch0=144 ch1=145

   Two channels, 144 and 145, 48kHz, 16-bit - precisely what the codec
   subscribes. That also closes the `SLIM_0_RX Channels = Two` lead: mainline has
   no such control because it derives the count from the codec's
   `get_channel_map`, and ours returns the right thing.

   **What remains is the per-port status byte.** Ours during playback against the
   golden reference, same stream, same routing:

        reg        ours   downstream
        030 INT_EN0  fc      ff        (ours masked by our own overflow handler)
        034 status   03      00
        060/061 src  01      00        OVERFLOW vs nothing
        040/041 cfg  05      05        identical
        080/081      42      20        <-- the unexplained difference

   `0x80+p` is defined in wcd9335's header as `SLIM_PGD_PORT_INT_STATUS(p)` but
   **never read anywhere in that driver**, so its bit meanings are not documented
   by any code we have. Ours has bits 1 and 6; downstream has only bit 5.

   **Correction to the golden reference:** the interface-device dumps in
   `docs/golden-reference/` only cover registers `0x00-0xBF`. `0x180`/`0x184`,
   the RX port channel map, were **never captured**, so the claim that they match
   cannot be made either way. Ours reads `03` at both. Re-capturing would mean
   wiping the install again, so treat that range as unknown.

   **The per-port status byte is not the clue it looked like.** Probed directly:
   `0x80`/`0x81` are **read-only** - writing the golden `0x20` does not stick -
   and they are **dynamic on our side**, reading `0x42` while a stream runs and
   **zero** at idle. Downstream's read a static `0x20` in *both* states. So the
   two are not the same quantity and the `0x42` vs `0x20` comparison does not
   mean what the earlier note implied. Bouncing the port enable while the chain
   runs does not move it either. Without documentation for those bits - wcd9335
   defines the register and never reads it - there is nothing further to get
   from it.

   **The MCLK pin function is a dead end too.** `pin 14 (gpio15)` shows
   `(MUX UNCLAIMED)` with the GPIO claimed by our driver, so it is driven as an
   ordinary output. That looked suspicious, but **downstream does exactly the
   same** - `gpio_request(pdata->mclk_gpio, "TAIKO_CODEC_PMIC_MCLK")` in
   `msm8974.c` - and downstream works. Plain-GPIO-high is correct; `func1` is not
   the answer. (The pinctrl `pinmux-select` route also refuses with EINVAL while
   the pin is held as a GPIO, so it cannot be tested that way regardless.)

   **A tooling trap worth knowing:** writing to sysfs/debugfs from Python
   reports failure at **close**, not at `write()`, because the write is buffered.
   A `try/except` around the write catches nothing and the script reports
   success. Three "no change" results were produced this way before it was
   spotted. Use `os.write()` on a raw fd, or check the exception at close.

   **So what is left** is whatever tells the codec's port logic to start pulling
   from an enabled, correctly-configured, correctly-fed slave port. Every layer
   around it has now been measured and is correct: the bus transactions, the DSP
   port config, the channel map, the rate maths, every codec register on the
   path, and the analog supplies. The remaining candidates all sit inside the
   WCD9320 itself and none of them is visible from software we have - which is
   the honest state of this investigation. Every
   *static* register on the path now matches downstream; the gap is more likely a
   missing step in the enable *sequence* or its ordering. The next thing to try
   is capturing what downstream actually writes, in order, during a working
   playback - `taiko-downstream.c` and `taiko-clsh.c` are in the scratchpad, and
   `wcd9xxx-slimslave.c` is in `downstream/`.

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

   **Loose ends.** The controller **used to** log `Error Interrupt received 0x82000000`
   (**stale as of 2026-10-01 - it no longer happens at all; it decoded to
   TX_MSG_SENT | TX_NACKED_2, see the dated note later in this section**)
   during stream setup. `SLIM RX3`..`RX7 MUX` warn "has no paths", which is
   expected while only RX1/RX2 are routed. Capture is **no longer** absent - `0067`
   added a capture DAI and `tx_chs`, so the old "Not able to allocate memory for 0
   slimbus tx ports" is not a fault.

   **Boot gets slow if the codec is blacklisted**, because the card's dai-links
   then wait on a device that never arrives; one boot took about seven minutes and
   another had to be power-cycled. With the codec loading normally that goes away.
   If it ever has to be blacklisted again, drop the `sound` node with it.

   **The MCLK pin is muxed wrong, and this is measured, not inferred.** The
   codec's master clock reaches the Taiko on **PM8941 GPIO 15**, and downstream's
   own device tree - read straight out of the LineageOS `boot.img` with
   `tools/romdtb.py` - configures that pin as a *special function*, not as a
   GPIO:

        /soc/sound
          qcom,cdc-mclk-gpios     = <phandle 15 0>
          qcom,taiko-mclk-clk-freq = 0x927c00      (9,600,000)

        /soc/.../qcom,pm8941@0/gpios/gpio@ce00     (pin 15)
          qcom,mode      = 1   digital output
          qcom,src-sel   = 2   QPNP_PIN_SEL_FUNC_1
          qcom,vin-sel   = 2
          qcom,pull      = 5   no pull
          qcom,master-en = 1

   Mainline encodes that field identically - `pinctrl-spmi-gpio`'s function
   index 2 is `"func1"` - and on this phone the register reads:

        MODE_CTL (0xce40) = 0x21   ->  value 1, function 0 ("normal"), dir in/out
        DIG_VIN_CTL      = 0x00   (downstream: 2)
        DIG_PULL_CTL     = 0x04   pull down   (downstream: 5, none)

   Function 0 means the pin emits the GPIO's DC level. Every other ordinary GPIO
   on this PMIC is `src-sel = 0`; the MCLK pin is one of the few downstream sets
   to `func1`. So the codec has been fed a static high where it needs 9.6MHz.

   **This is consistent with the entire investigation.** Register access rides
   the SLIMbus clock and needs no MCLK, which is exactly why every register on
   the path compares equal to downstream while the RX port never drains: the
   codec's digital clock tree has no source, so nothing pulls from an enabled,
   correctly-fed slave port.

   **The earlier dismissal of this lead was wrong, and the reason is worth
   keeping.** It rested on downstream also calling
   `gpio_request(pdata->mclk_gpio, "TAIKO_CODEC_PMIC_MCLK")` in `msm8974.c`. It
   does - but `gpio_request()` only *claims* the pin; the mux comes from the DT
   pin config, which is a different mechanism and was never checked. "Downstream
   does the same thing" is only an argument if you have compared the same layer.

   **The rate question is now closed too.** Downstream does `clk_get(cpu_dai->dev,
   "osr_clk")` then `clk_prepare_enable()` and **never calls `clk_set_rate`** -
   identical to this port. So the `div_clk1` rate mislabel (19.2MHz in the
   mainline clock table) is not a difference between the two stacks, and the
   PMIC-divider route stays closed. The clock is also genuinely enabled on our
   side: `/sys/kernel/debug/clk/div_clk1/clk_enable_count` is `0` at idle and
   **`1` during playback**, so `clk_prepare_enable()` works. Only the pin is wrong.

   **Poking the mux live is not enough on its own.** Writing `MODE_CTL = 0x15`
   (dir out, func1, value 1) plus `VIN = 2` and `PULL = 5` mid-session makes the
   pin's readback follow `div_clk1`'s enable state instead of the GPIO level -
   1 while idle, 0 once the clock is enabled, where the "normal" control reads a
   constant 1 - so the mux does reach the pin. **The overflow is unchanged.**
   That is not a refutation: the codec had already come out of reset and run its
   whole register init with no clock. The test that matters - first init with the
   mux already correct - has **not** been run yet, because unloading the codec
   oopsed (see `0065`).

   Note the readback cannot prove a 9.6MHz square wave either way: the PMIC
   samples its input through a much slower synchroniser, so a constant 0 is what
   a clock and a dead pin both look like. Treat the pin state as "changed", not
   as "clocking".

   **`0065` fixes a remove path that oopsed every module unload.**
   `wcd9320_remove()` called `clk_put(wcd->codec_clk)` on a clock it does not
   own - `wcd9320_parse_dt()` takes it with `devm_clk_get()` on the **slim**
   device and probe only copies the pointer - so it dropped a reference this
   device never took and devm put it again on the way out. The trace is
   `__clk_put` <- `wcd9320_remove` <- `platform_remove`. It also called
   `devm_kfree()` on the devm-allocated private data *before*
   `snd_soc_unregister_component()`, leaving the component's callbacks running
   against freed memory. Both are gone; unregister is all that is needed. Until
   this is installed, **do not `modprobe -r snd_soc_wcd9320`** - the oops leaves
   the thread in `D` state holding `module_mutex`, which hangs every later
   `lsmod` and `modprobe`.

   **A single PMIC register can be read after all, and this supersedes the
   "0-01 is unusable" note.** The warning elsewhere in this file is about reading
   the *whole* file; `regmap` debugfs supports seeking, and the dump is a fixed
   9 bytes per line (`"ce40: 21\n"`), so a window can be read directly:

        # register R is at byte offset R*9; pick a bs that divides it
        dd if=/sys/kernel/debug/regmap/0-00/registers bs=144 skip=3300 count=1
        ->  ce40: 21 ... ce4f: 00     (0xce40 = 52800, 52800*9 = 3300*144)

   `bs` must be at least one line long or `read()` returns 0 and `dd` prints
   nothing - `bs=1` silently yields an empty result, which reads like a failed
   permission rather than a too-small buffer. `0-00` is pm8941 SID 0, range
   `0-ffff`, every register readable, and it takes writes as well
   (`echo "ce40 15" > .../registers`) with the debug patch in place.

   **Three reboot traps, all hit in one session.** `/proc/sys/kernel/sysrq` is
   **16** here - sync only - so `echo b > /proc/sysrq-trigger` does nothing at all
   and prints no error; set it to `1` first, in the *same* shell, because the
   value is back to 16 on the next login. `sudo systemd-run --no-block` hangs
   once `systemd-journald` has been killed, so it is not a reliable way to
   outlive the ssh session when the system is already degraded. And plain
   `sync(1)` can block for minutes on a wedged filesystem, which silently eats
   the `timeout` budget of whatever was meant to run after it - put the sysrq
   writes first, not last.


   **RETRACTION: the MCLK pin mux is a real defect but it is NOT the cause.**
   The test the section above says was never run has now been run, on r114, and
   it is negative. With `MODE_CTL/VIN/PULL` held at downstream's exact values
   (`15 02 05`) by a 50ms writer loop across the codec's *first* init of the
   boot, `div_clk1` enabled, and liveness asserted on every reading:

        run 1..5: INT_STATUS_RX_0=03  pcm=RUNNING  procs=1  pin=15 02 05

   Unchanged. Fix the mux anyway - it genuinely disagrees with downstream - but
   it is not what stops the data.

   **And the clock is not the variable at all.** The pin test alone could not
   separate "MCLK is fine" from "func1 is not the clock", so the codec's own
   **RC oscillator** was used as the control: it is internal, needs no pin, and
   is unquestionably present. Switched mid-playback with the full bring-up -
   `BIAS_OSC_BG_CTL=0x17`, `RC_OSC_FREQ` bit7, the `RC_OSC_TEST` pulse,
   `CLK_BUFF_EN1` bit3 set and bit2 cleared (`0x05 -> 0x09`), **including the
   `CLK_BUFF_EN2` reset pulse** that the first attempt wrongly left out - the
   overflow reads `0x03` on every probe, identical to MCLK. The RCO also runs at
   a different frequency, so a clocked-but-wrong-rate core would have shown
   *under*flow. It showed nothing of the sort. The codec's digital core is not
   sitting unclocked, and the whole MCLK line of reasoning is closed.

   **A full two-space register diff against the golden reference now exists**,
   and it is the strongest version of the "registers are not the problem"
   claim. All 666 PGD registers, ours playing against
   `codec_reg-HPH-PLAYING.txt`: **67 differ**, and every one of them is MBHC
   (`3c0`-`3dc`, `14a`-`14f`, `171`-`174`), mic bias (`129`-`13d`), the TX ADCs
   (`153`-`169`), IIR/ANC/PA-ramp (`340`-`364`, `28d`), analog gains
   (`1aa`-`1d9`), interrupt masks (`090`-`0af`, ours masked by our own overflow
   handler) or read-only fuses. Downstream runs subsystems this port does not;
   **not one register on the RX data path differs.**

   The interface device is the same story. Ours playing against
   `ifd-HPH-PLAYING.txt`, `0x00-0xBF`: only `030` (our masking), `034` and
   `060/061` (the overflow itself) and `080/081` differ. **`040 = 05` and
   `041 = 05`, matching downstream exactly** - an earlier spot-check that read
   `041`/`042` and reported "port 2 not enabled" was reading the wrong pair,
   since our ports are 0 and 1.

   **Two more candidates killed by live poke.** `LDO_H_MODE_1` is the one
   non-MBHC analog difference - ours `0x6d`, downstream `0xed`, identical but
   for bit 7 - and writing `0xed` mid-playback (confirmed by readback) changes
   nothing. And the **supplies are right**: our DT maps them exactly as
   downstream does (`vdd-buck`->s2, `vdd-rx-h`/`vdd-tx-h`/`vddpx-1`->s3,
   `vdd-a-1p2v`/`vddcx-1`/`vddcx-2`->l1), and on the phone `s2=2150000`,
   `s3=1800000`, `l1=1225000` are all enabled with users, which are downstream's
   own voltages to the microvolt.

   **`0066` makes the codec reloadable, which changes how this is worked on.**
   With `0065` the module unloads cleanly, but the *reload* then oopsed at
   `wcd9320_probe+0x68`: the codec's platform device is created by
   `of_platform_populate()` from the slim status callback and nothing
   depopulates it, so it outlives the unload, and on the next load the platform
   driver is matched against that leftover device before the slim device has
   probed and set its drvdata - `control` is NULL and probe writes through it.
   `0066` returns `-EPROBE_DEFER` in that case. Together the two mean a codec
   change can now be tested with `unbind card; modprobe -r; modprobe; bind card`
   instead of a reboot per iteration.

   **Where that leaves it.** Data demonstrably arrives at the right ports, the
   codec consumes none of it, and every layer that can be read has now been
   compared against a working reference and matches: both register spaces, the
   clock (by substitution, not by inspection), the supplies and their voltages,
   the bus transactions, the DSP port config and the rate maths. The one layer
   never compared against downstream is **what the SLIMbus manager is told, and
   what the codec is told, about the channel**. `slim_stream_enable()`
   short-circuits into `qcom_slim_ngd_enable_stream()`, which packs everything
   into one `SLIM_USR_MC_DEF_ACT_CHAN` QMI message to the ADSP rather than
   emitting DEFINE_CHANNEL/ACTIVATE_CHANNEL on the bus. That was written off as
   "expected, not a bug", and it is expected - but nobody has checked that the
   resulting channel definition matches what `CONNECT_SINK` bound on the codec
   side. Downstream's `slim-msm-ngd.c` sends its own version of the same QMI
   message; diffing the two payloads is the same kind of source-level comparison
   that turned up the pin mux, and it is the next thing to do.

   **Correction to the recovery instructions elsewhere in this file:** powering
   this phone off is **Power + Volume Up**, not a ten-second power hold, which
   does nothing.


   **Two leads chased and closed 2026-10-01, both recorded so nobody repeats them.**

   *The NGD "Error Interrupt received 0x82000000" is stale.* It is listed further
   down as a loose end, and it decodes to something that looked very promising
   once the fault was known to be direction-agnostic:

        0x82000000 = NGD_INT_TX_MSG_SENT (BIT 31) | NGD_INT_TX_NACKED_2 (BIT 25)

   bit 25 being a message **not acknowledged by the target device** - exactly the
   shape of a setup message being rejected while ordinary register traffic works.
   But it **no longer happens**: zero "Error Interrupt received" since boot and none
   during a playback that still overflows. It was from an earlier build and one of
   `0053`-`0056` evidently fixed it. The bus layer now reports no errors at all.

   *Mainline does no SLIMbus bandwidth or clock-gear management, and that is
   probably fine.* Downstream's core computes a required clock gear from the
   scheduled channels and sends it; mainline has none of that machinery - no
   `usedslots`, no `slim_reconfigure_now`, no gear computation - and the NGD simply
   does

        ctrl->ctrl.clkgear = SLIM_MAX_CLK_GEAR;    /* once, at probe */

   Worth knowing as a real architectural difference, but max gear is the generous
   choice: one stereo 48kHz channel is far inside it. Not a plausible cause of
   zero data.

   **2026-10-01, the sharpest statement of the fault so far: the codec moves no
   data in EITHER direction, while register access over the same bus is perfect.**

   The capture side was poked by hand, with no driver changes, down the only chain
   SB TX port 0 can carry - `ADC6 -> DEC1 -> port 0` (port 0 offers only DEC1 or
   RMIX, and DEC1 accepts only DMIC1 or ADC6). Every register confirmed by
   readback, and MCLK confirmed running at `div_clk1 enable_count = 1` by keeping a
   playback open alongside:

        30c=03  ADC block clock      13d=f6  micbias4 enabled
        167=0a  TX_5_6_EN            169=82  ADC6 enabled
        393=02  DEC1 <- ADC6         30a=01  DEC1 clock
        223=40  ADC source (not DMIC) 3a3=08  SB TX port 0 <- DEC1
        311=01  CDC_CLK_MCLK_CTL

   Capture: **exactly zeros**, with the ADC on, with it off, and on again.

   **MCLK was a real confound and is now excluded.** `div_clk1` is only enabled
   while playback runs, and the capture path added by `0067` has no MCLK supply
   route - so the first version of this test had no clock for the decimator at all.
   Repeating it with a playback open fixes that, and changes nothing.

   **What this buys.** Put it beside the RX result and the fault is direction
   agnostic: the RX port **fills and is never drained** (overflow, and that bit was
   validated against a control - an enabled port with nothing feeding it does not
   overflow), and the TX port **is never filled**. Bus-level delivery demonstrably
   works, because data arrives at the RX port. What does not work is the codec's own
   side of its data ports.

   That retires, in one go, every hypothesis specific to the RX chain: the
   interpolators, Class-H, the DSM/DAC, the mixer routing, the RX port sample
   width, and the MCLK pin mux. Any remaining explanation has to be something the
   two directions share - the codec's port engine, or how its data channels are
   established on the bus.

   **Honest limit of this result.** The hand-poked TX chain is not a validated
   instrument either; it could in principle be missing a decimator rate or width
   setting. What is validated is the RX overflow bit, so "data arrives and is not
   consumed" is solid, and "and nothing comes back the other way" is strong
   corroboration rather than proof.

   **The RX-to-TX loopback: a good idea that is still unmeasurable, and why the
   microphone is now the blocking piece.** A SLIM TX port can carry more than a
   decimator. From downstream's own mux:

        sb_tx1_mux_text = { "ZERO", "RMIX1".."RMIX7", "DEC1" }
        CONN_TX_SB_B1_CTL (0x3a3) shift 0: 0=ZERO, 1..7=RMIX1..RMIX7, 8=DEC1

   `RMIX1` is the **RX1 mixer output** - the playback path. So the codec can loop
   playback back to the AP over SLIMbus with no microphone involved, which looked
   like the bisection that had been impossible to measure: play on RX1, capture
   RMIX1, and non-zero would prove the RX chain carries data internally.

   Run properly - playback confirmed `RUNNING` across all five captures, each four
   seconds - every setting gives zeros:

        ZERO -> zeros   RMIX1 -> zeros   RMIX2 -> zeros   DEC1 -> zeros   ZERO -> zeros

   **And that cannot be interpreted.** The capture path has never been shown to
   carry *any* data: with the TX slave port outright **disabled** it still returned
   byte-identical zeros. So uniform zeros is exactly what a dead capture path
   produces whatever RMIX1 holds. The result is *consistent* with the RX chain
   carrying nothing, and proves nothing.

   **What is missing is a positive control** - a signal known to be non-zero
   arriving on a SLIM TX port. The TX mux offers only RMIX1-7 (which needs RX to
   work, so circular) and DEC1 (which needs a decimator fed by a real
   microphone). There is no internal test tone. So the analog capture path is not
   just a feature any more: **it is the only way to get an instrument**, and
   without it no capture-side measurement on this codec means anything.

   That makes the microphone the next piece of work, and gives it a sharper
   purpose than "the phone should have a mic".

   **A SLIMbus capture path now exists (`0067`, `0068`), and the bisection it was
   built for is inconclusive.** The idea was to test the CDC-to-port interface
   in the other direction: the overflow already proves the port engine's
   *receive* half works, since bus data really does land in the port FIFO, so
   what is broken is specifically the transfer from that FIFO into the CDC. If
   the codec could fill a TX port, the interface works and the fault is
   RX-specific.

   `0067` adds the codec half: the `tx_chs` table (the card was already passing
   `tx_ch[] = {128, 129, ...}` to `set_channel_map` and it was being dropped
   because `tx_chs` was NULL), a capture DAI, a `SLIM TX1 MUX` to subscribe a
   channel, an `enable_slimtx` widget handler, and `wcd_slim_tx_stream_prepare()`
   as a **separate function** rather than a direction flag on the RX one - the RX
   path is the only thing that works as far as the bus and it was not worth
   risking to save the duplication. `0068` adds the two dai-links the card needs
   (`MultiMedia2` frontend, `SLIMBUS_0_TX` backend on codec DAI index 1); without
   them `arecord` listed no capture devices at all. That one needs a **boot image
   flash**, since it is device tree - it went in cleanly and the phone booted in
   90 seconds.

   **It works as far as it goes:** `card 0, device 2: MultiMedia2` appears, the
   stream runs, and our TX port registers are written correctly - `cfg 0x50 =
   0x05`, `chmap 0x100 = 0x01`.

   **But both instruments failed their controls, so nothing can be concluded.**

   - *TX port status is not an instrument.* `INT_STATUS_TX_0` reads `0x00` in
     every condition, including with the decimator's clock switched **off**
     mid-capture, which starves the port and should underflow. The TX interrupts
     are genuinely enabled (`INT_TX_EN0` is `0x30 + 2` = `0x32`, reading `0xff`),
     so this is not a masking artefact - the bit simply never asserts. Note the
     RX side reports overflow and port-closed reliably, so this asymmetry is
     itself unexplained.
   - *The captured audio is not an instrument either.* With the TX slave port
     **disabled** (`cfg 0x50 = 0x04`), `arecord` still produced a byte-identical
     384044-byte file of zeros. The ADSP manufactures a well-formed 48kHz stream
     whether or not the codec contributes anything.

   **What it would take to finish.** Real, non-zero audio from the codec, which
   means an analog mic path: micbias, the ADC enable, and the decimator input
   mux. The golden reference cannot shortcut this - downstream was playing to
   headphones when it was captured and had **no TX path active** (`0x30a = 0x00`,
   TX clock off), so there are no known-good TX values to copy. That is
   implementing capture properly rather than running an experiment, and it is the
   same work the microphone needs, so it is not wasted - but it should be chosen
   as a feature, not as a probe.

   **A bug worth not repeating, introduced and fixed here.** The first version of
   `slim_tx_mux_put()` called `list_add_tail()` without checking whether the node
   was already linked. Setting the control twice spliced the channel list into a
   **cycle**, and `wcd9320_get_channel_map()` then walked it forever, writing past
   the end of the caller's 16-entry `tx_slot[]` array - a stack smash inside
   `msm_snd_hw_params()`, whose trace came back with the return address
   overwritten by `0x80`, which is `BASE_CH_NUM`, the value being written. The RX
   mux guards this with `wcd_slim_rx_vport_validation()`. The fix makes the
   subscribe idempotent. **Any list_add on these shared channel nodes needs that
   guard.**

   **Operational note: do not unbind and rebind the card to reload the codec.**
   `0065` and `0066` make `modprobe -r` and `modprobe` work, but
   `echo sound > .../bind` afterwards oopsed in `regmap_write` inside the
   component probe. That path has never once completed successfully. Test codec
   changes on a **fresh boot** instead - and note that every oops here is followed
   by a reboot that wedges with sshd never starting, which costs a physical
   power-cycle (**Power + Volume Up**).


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

## Camera: bigger than audio, but the CAMSS half is much smaller than it looked

Surveyed properly 2026-10-03 against the LineageOS device tree, and the conclusion from
the first pass needs revising: **the CAMSS block is the same generation as msm8916's,
which mainline already supports.** The register offsets inside the CAMSS window are
*identical*; only the base address differs.

        block              msm8916 (supported)   amami / msm8974
        csiphy0            0x01b0ac00  0x200     0xfda0ac00  0x200
        csiphy0_clk_mux    0x01b00030  0x4       0xfda00030  0x4
        csid0              0x01b08000  0x100     0xfda08000  0x100
        ispif              0x01b0a000  0x500     0xfda0a000  0x500
        csi_clk_mux        0x01b00020  0x10      0xfda00020  0x10
        vfe0               0x01b10000  0x1000    0xfda10000  0x1000

So the base is 0x01b00000 there and 0xfda00000 here, and every offset within it matches.
Downstream calls the VFE `qcom,vfe40` and the ISPIF `qcom,ispif-v3.0`. msm8974 simply has
**more instances**: 3 CSIPHY (vs 2), 4 CSID (vs 2), 2 VFE (vs 1), plus CPP and three JPEG
blocks that are not needed for capture.

**And the supporting plumbing already exists in mainline.** Every clock the subsystem
needs is already in `include/dt-bindings/clock/qcom,mmcc-msm8974.h`: `CAMSS_CSI0..3_CLK`,
`CAMSS_VFE_VFE0/1_CLK`, `CAMSS_CSI_VFE0/1_CLK`, `CAMSS_CCI_CCI_CLK`,
`CAMSS_PHY0..2_CSI0..2PHYTIMER_CLK`, `CAMSS_ISPIF_AHB_CLK`, `CAMSS_TOP_AHB_CLK`, and the
`*_CLK_SRC` parents. `CAMSS_VFE_GDSC` and `CAMSS_JPEG_GDSC` exist for `power-domains`.
Nothing new is needed from mmcc.

**How much driver work that leaves:** `CAMSS_8x16` appears only 8 times across 5 files, so
the per-SoC switching is light. A msm8974 port is plausibly a `CAMSS_8x74` enum value,
resource tables for 3 CSIPHY / 4 CSID / 1 ISPIF / 2 VFE reusing `csiphy_ops_2ph_1_0`,
`csid_ops_4_1`, `vfe_ops_4_1` and the existing ispif code, and a DT node. That is a
moderate, mostly-mechanical job - **not** a new VFE driver, which is what the earlier note
implied. It wants verifying rather than assuming: the identical register map makes 4-1 ops
*likely* to fit VFE40, not certain.

### The sensors are the hard half, and the rear one has no mainline driver

Pulled from the Lineage DT, `qcom,cci@fda0c000` (CCI itself matches mainline's CCI driver
shape - `reg 0xfda0c000 0x1000`, one interrupt, two I2C masters):

        rear   qcom,camera@20   sony_camera_0   CCI master 0, CSIPHY/CSID index 0
               4 data lanes (lane-mask 0x1f), MCLK = GPIO 15, RESET = GPIO 94
               cam_vdig 1.2V, cam_vana 2.7V, cam_vio (fixed), cam_vaf 2.8V
               modules: SOI20BS0 (default), SOI08BS2
               5248 x 3936 = 20.7 MP, diagonal 7.87 mm (1/2.3"), 1.20 um, f/2.0
               subdev_code 0x3007 = MEDIA_BUS_FMT_SBGGR10_1X10

        front  qcom,camera@6c   sony_camera_1   CCI master 1, CSIPHY/CSID index 2
               2 data lanes (lane-mask 0x7), MCLK = GPIO 17, RESET = GPIO 18
               cam_vdig 1.2V, cam_vana 2.7V, cam_vio (fixed), no VAF
               modules: SEM02BN1 (default), LGI02BN1 - 2 MP class, diagonal 2.59 mm

**The rear part is almost certainly a Sony IMX220** - 20.7 MP at 1/2.3" with 1.2 um pixels
is that sensor and little else - but that is an *inference from geometry*, not a reading,
and it is worth stressing because mainline has no `imx220` driver (it has imx208, 214,
219, 258, 274, 283, 290, 296, 319, 334, 335, 355, 412, 415). The module codes are module
vendors, not parts: `SOI` is Sony, `LGI` LG Innotek, `SEM` Samsung Electro-Mechanics, so
the front module vendor varies between units while the sensor inside may not.

**Confirming the part is itself a good milestone**, and it comes before any sensor driver:
bring up CCI, power the sensor per the sequence the DT already spells out, and read its ID
register. The DT carries the exact per-module `power_on`/`power_off` command lists and PLL
tables, which is a real gift - the ordering does not have to be guessed.

### Step 1 attempted 2026-10-03: the patches exist, and the kernel stopped booting

**What is solid, and worth keeping whatever happens to the boot problem.** All of this was
read out of the Lineage DT and cross-checked, and none of it depends on the patches working:

- the register map above, and the CAMSS base of 0xfda00000;
- **the interrupts, confirmed three independent ways.** Downstream writes `<0 N 0>` =
  `<GIC_SPI N ...>`, so the numbers need no offset - verified because downstream's SPMI is
  `0xbe` = 190 and mainline msm8974.dtsi independently has that arbiter at `GIC_SPI 190`.
  They also match msm8916's CAMSS SPIs exactly, and mainline's *existing* `cci@fda0c000`
  node already uses `GIC_SPI 50`, which is downstream's `0x32`. csiphy0-2 = 78/79/80,
  csid0-3 = 51/52/53/54, ispif = 55, vfe0/1 = 57/58, cci = 50.
- **every clock exists in `qcom,mmcc-msm8974.h`**, and the rates are msm8974's own, from
  the mmcc driver: CSI0-3 and the CSIPHY timers offer 100/200 MHz, VFE has its own
  13-entry table from 37.5 to 465 MHz.
- **the regulators, resolved from downstream's phandles:** CSI `vdda` is `8941_l12` at a
  fixed 1.8V. For the sensors later: vdig `8941_l3` 1.2V, vana `8941_l17` 2.7V, vio
  `8941_lvs2`, vaf `8941_l23` 2.8V. The VFE's `vdd` is the `gdsc_vfe` domain, i.e.
  `CAMSS_VFE_GDSC`.
- **mainline already has a complete `cci@fda0c000` node**, both I2C buses and pinctrl,
  only `status = "disabled"`. Step 2 is therefore much closer than it looked.

**A blocker that explains why no msm8974 CAMSS exists, and that the first survey missed.**

        config VIDEO_QCOM_CAMSS
                depends on (ARCH_QCOM && IOMMU_DMA) || COMPILE_TEST
        config IOMMU_DMA
                def_bool ARM64 || X86 || S390

`IOMMU_DMA` cannot be selected on 32-bit ARM at all. Every SoC this driver supports is
arm64; msm8974 would be the first arm32 one. So this is not only a missing resource table,
it is an architectural assumption - which makes the earlier "step 1 is a weekend" estimate
wrong. `debug/9006` drops the dependency for bring-up and says in the file that it is not
shippable: with no IOMMU there is no way to hand `dma-sg`'s scattered pages to the VFE.
Real capture will want the CAMSS IOMMU, and the downstream DT does show two SMMUs at
`0xfda44000` and `0xfda64000`, which connects this to the parked IOMMU work.

**And the kernel does not boot with these patches in, cause not yet identified.**

        build  media config  camss module  camss DT node  boots
        r140   off           absent        absent         YES
        r142   on            yes           enabled        no
        r143   on            yes           disabled       no

r143 is the informative one and it refutes the obvious theory: a `disabled` node creates no
platform device and no fw_devlink edges, so the DT node is largely exonerated, and the
driver is a module so its code is not in the kernel proper. The effective-config diff
(both apks ship `boot/config`, so the post-`syncconfig` result can be compared directly)
shows 24 new built-ins that are all inert media core - `DVB_CORE`, `MEDIA_TUNER`,
`V4L2_FWNODE`, `VIDEO_DEV` and so on - 159 new modules, and nothing removed or downgraded.
Ruled out and worth not re-checking: the boot partition is 20 MiB against an 18.38 MB
image; the kernel grew only 116 KB and the ramdisk loads 33 MB above it; the compiled DTB
is well-formed, 31 clock pairs all resolving to mmcc with matching `clock-names`.

**Resolved 2026-10-03: it was the media config, and the camera patches were innocent.**

        build  media config      camss patches  camss node  boots
        r140   off               no             absent      YES
        r142   built in (=y)     yes            enabled     no
        r143   built in (=y)     yes            disabled    no
        r144   built in (=y)     no             absent      no
        r145   modular (=m)      yes            disabled    YES
        r146   modular (=m)      yes            enabled     YES

r144 is the decisive row: no camss code, no node, and a `vmlinuz` byte-for-byte the same
size as r143's - it still failed. So turning the media subsystem on *built in* is what stops
the boot. r145's kernel is one page larger than r140's, against r144's 116 KB, which is the
whole point: nothing media-related is in the kernel proper any more.

**"Does not boot" was confirmed for free, without looking at the screen.**
`journalctl --list-boots` on the recovered system shows no boot at all for r142, r143 or
r144 - the gaps between recorded boots line up exactly with each failed attempt. So none of
them reached userspace, and since the phone never appeared even as the initramfs' USB debug
shell, the failure is before that too. It was not a dead USB gadget.

**Which built-in symbol does it is not known**, and it was not worth finding out: 24 new
built-ins, all media core (`DVB_CORE`, `MEDIA_TUNER`, `RADIO_ADAPTERS`, `V4L2_FWNODE`,
`VIDEO_DEV`...), none of which obviously probes anything at boot. They came in because
`syncconfig` defaulted the TV, radio, SDR and test menus on. The camera needs none of it.

**Then the first probe found a latent clock bug.** With the node enabled the driver bound,
created `/dev/media0` and `/dev/video0-5`, and logged `clk round rate failed: -2` /
`Failed to power up pipeline: -22` twelve times. `-ENOENT` from `clk_round_rate()` on a qcom
RCG comes from `qcom_find_src_index()`: a freq-table entry whose source is not in that
clock's parent map. `ftbl_camss_vfe_vfe0_1_clk` lists `F(465000000, P_MMPLL3, 2, 0, 0)`, but
`vfe0/1_clk_src` use `mmcc_xo_mmpll0_mmpll1_gpll0_map`, which has no `P_MMPLL3`. So 465 MHz
can never be resolved - a bug in mmcc-msm8974, exposed because the VFE rate list was copied
straight from that table. `0085` now stops at 400 MHz (MMPLL0).

**Verified with a positive control**, since zero errors on a reload proved nothing - nothing
had opened the nodes. Opening a video node is what powers its pipeline up (it is the path
the twelve errors came from), so every node was opened and `VIDIOC_QUERYCAP` issued: all six
report `qcom-camss` / "Qualcomm Camera Subsystem", zero errors. Repeated from a fresh boot of
r148. **Step 1's milestone is met.**

Recovery each time was fastboot: Volume Up held while plugging in, then
`fastboot flash boot boot-images/boot-r140.img`. **And then `fastboot reboot`** - S1Boot
stays in fastboot until told otherwise, so after the flash the phone sits there looking
exactly like another failed boot. Only *entering* fastboot needs hands; everything after
it is remote.

### Suggested order, each step observable

1. ~~**CAMSS plumbing**~~ **DONE 2026-10-03 on r148** - `0085` (resources), `0086` (DT
   node), `0087` (enable on amami), `debug/9006` (arm32 bring-up), with the media config
   modular. Driver probes, six video nodes, pipelines power up clean. Still bring-up grade:
   `9006` drops the `IOMMU_DMA` dependency, and real capture will want the CAMSS IOMMU.
2. ~~**CCI and sensor identity**~~ **DONE 2026-10-03 on r155: the rear sensor is a Sony
   IMX200, not an IMX220.** See "Step 2" below.

### Step 2, 2026-10-03: the rear camera is an IMX200, read off the hardware twice over

**Method: borrow a driver rather than write one.** `debug/9007` describes the rear camera on
`cci_i2c0` at `0x10` as `sony,imx219` - wrong part on purpose - because imx219's probe powers
the supplies, starts the clock, releases reset and reads a 16-bit model ID, logging what it
found on a mismatch. `debug/9008` makes it also dump the SMIA ID header and the module EEPROM
while powered. Rails: VANA = `pm8941_l17` (2.7V), VDIG = `pm8941_lvs2`, VDDL = `pm8941_l3`
(1.2V), all pinned min=max by RPM at downstream's voltages, so the supply names cannot
mis-volt anything. `lvs2` had to be added to the RPM regulator block; rhine.dtsi never
declared it. Reset is GPIO 94, physically active low. Downstream's power-up order is VDIG,
VIO, VANA, VAF, release reset, then MCLK.

**The sensor ID register**, stable across two power cycles and identical through 8-, 16- and
24-bit reads:

        0x0000: 00 00 00 00 00 ff 01 00 00 40 00 00 0a 00 00 00
        0x0010: 00 00 00 00 00 00 02 00 01 00 00 00 00 00 00 00
                                  ^^^^^ ^^ model 0x0200, revision 0x01

**The module EEPROM** at 7-bit `0x50` (downstream's `sony,eeprom_addr 0xa0`), 1-byte
addressing, plain text:

        000: 53 4f 49 32 30 42 53 30 ...  |SOI20BS0|   module code = downstream's default
        020: 49 4d 58 32 30 30 30 41 ...  |IMX2000A|   the sensor
        030: 42 55 36 34 32 39 36 47 ...  |BU64296G|   ROHM BU64296G, the AF/VCM driver

The module code matching downstream's `default_module_name` exactly is the positive control:
it proves the whole path - CCI, the power sequence, the addressing - against a known string.
And the two readings agree: Sony's model IDs encode the part number (IMX135 -> 0x0135,
IMX214 -> 0x0214), so `0x0200` *is* IMX200. **The earlier IMX220 identification in this file
was an inference from geometry and repeated lore, and it was wrong.** For a while it looked as
though the register might be meaningless - the mainline IMX300 driver's author found that
Sony's custom Xperia sensor carries no part number at `0x0016` - but that is true of the
IMX300, not of this part. Mainline has no `imx200` driver either.

**Three hardware facts found on the way, each worth keeping:**

- **msm8974's camera MCLK RCGs have no M/N counter, so 24 MHz is unreachable**, and asking for
  it silently produces **120 MHz** - which would go straight into a sensor's INCK. mmcc-msm8974
  shares its `ftbl_camss_mclk0_3_clk` with apq8084, whose MCLK RCGs at the *same* `cmd_rcgr`
  do have M/N, so the 6/8/16/24/32 MHz entries (`F(24000000, P_GPLL0, 5, 1, 5)` etc.) cannot
  be produced here; the RCG picks GPLL0/5 and skips the M/N stage. This was nearly "fixed"
  the wrong way: adding `.mnd_width = 8` (the parked-then-deleted `0088`) changed nothing,
  and hand-written M values do not latch. The proof that this is missing hardware and not a
  root-off effect is a control in the same off state: `camss_gp0`'s M register at `0x3428`
  *does* latch a written 1, while `mclk0` (`0x3368`) and `mclk1` (`0x3398`) read back 0, and
  CFG writes latch fine on both. Reachable MCLK rates are the XO ones (4.8, 9.6, **19.2 MHz**)
  and plain dividers (48, 64, 66.67 MHz). The bring-up uses 19.2 MHz, which is enough for I2C;
  `debug/9008` lets imx219 accept it. A real IMX200 driver will need PLL settings for an INCK
  this SoC can actually make - the DT's per-module `pll` tables are where to look.

  **Fixed by `0090` (r160, 2026-10-04):** msm8974's `ftbl_camss_mclk0_3_clk` now lists only
  those six reachable rates; the five M/N entries are gone, and msm8226's own table is
  untouched. Verified on hardware rather than from the code: a test build pointed the front
  camera at 24 MHz, and MCLK2 came out at **48 MHz**, the next real rate up - with the clock
  framework and the hardware agreeing (CFG `0x33c4` = `0x518`, GPLL0 / 12.5). Before the fix
  the same request produced 120 MHz. imx219 refused the 48 MHz before powering anything, and
  the rear at 19.2 MHz still read its ID and EEPROM. So a sensor driver asking for 24 MHz now
  gets an honest answer it can check. The front went back to 19.2 MHz for r161.
- **The VFE table has a sibling bug that is recorded, not patched.** Its 465 MHz entry sources
  MMPLL3, which msm8974's `vfe0/1_clk_src` parent map does not include, so the rate fails with
  `-ENOENT` (`0085` stops at 400 MHz for that reason). apq8084, which shares the table, makes
  465 MHz from **MMPLL4** through a different map; msm8974 has no MMPLL4. Whether msm8974's VFE
  mux can really reach MMPLL3 cannot be checked without measuring the clock, so neither the
  table nor the parent map is changed. Unlike the MCLK bug, this one fails safely.
- **msm8974's CCI caps a read at 12 bytes and a write at 10** (`cci_v1_5_data`), and the I2C
  core returns `-EOPNOTSUPP` for anything longer - a 64-byte EEPROM read fails outright.
- **The CSIPHY lane mapping** from downstream's `csi-lane-assign 0x4320` and
  `csi-lane-mask 0x1f`: data on CSIPHY lanes 0, 2, 3, 4 with the clock on 1. It is in the camss
  endpoint already; nothing has streamed yet, so it is unverified.

The rear module also has a second variant, `SOI08BS2`, which this phone does not carry.

**The front camera is a Sony IMX132**, identified the same way on r156 (`debug/9007` now
describes both cameras). It sits on CCI master 1 (`cci_i2c1`) at 7-bit `0x36`, MCLK on GPIO 17
(`cam_mclk2`, run at 19.2 MHz), reset on GPIO 18, the same three rails, 2 data lanes on
CSIPHY 2 (clock lane 1, data 0 and 2), no focus actuator, 1976x1200 at 1.12 um.

        sensor 0x0000: 01 32 02 0b 0a ff 01 00 00 40 ...   model 0x0132, rev 0x02,
                                                           manufacturer 0x0b = Sony
        EEPROM  000: |SEM02BN1|  020: |IMX132|             module = downstream's default

The two sensors explain each other: the older IMX132 keeps its model ID at the classic SMIA
location `0x0000`, with Sony's manufacturer code `0x0b` at `0x0003`, while the IMX200 uses
`0x0016` and leaves `0x0000` empty - which is exactly why the rear first read 0. imx219 itself
printed `chip id mismatch: 219!=132` for the front. Mainline has no `imx132` driver.

### Test-pattern capture, 2026-10-04: frames reach memory through the whole pipeline

The CSID 4.1 block has a built-in test-pattern generator (`test_pattern` menu on the CSID
subdev: incrementing, 0x55/0xAA, zeros, ones, pseudo-random, user). That makes it possible to
prove CSID -> ISPIF -> VFE RDI -> DMA works before writing any sensor driver:

        media-ctl -d /dev/media0 -l '"msm_csid0":1->"msm_ispif0":0[1],"msm_ispif0":1->"msm_vfe0_rdi0":0[1]'
        v4l2-ctl -d /dev/v4l-subdev3 -c test_pattern=4          # set BEFORE the formats
        media-ctl -d /dev/media0 -V '"msm_csid0":1[fmt:SBGGR8_1X8/64x32 field:none],"msm_ispif0":0[fmt:SBGGR8_1X8/64x32 field:none],"msm_vfe0_rdi0":0[fmt:SBGGR8_1X8/64x32 field:none]'
        v4l2-ctl -d /dev/video0 --set-fmt-video=width=64,height=32,pixelformat=BA81
        v4l2-ctl -d /dev/video0 --stream-mmap=4 --stream-count=6 --stream-to=out.raw

Six frames per pattern, and each capture is exactly its pattern while the three differ from
one another - so the bytes came off the generator, not out of stale buffers:

        All Ones      12288 x ff
        All Zeros     12288 x 00
        Alternating   6144 x aa + 6144 x 55

Two things had to change first. **camss waits forever on sensor endpoints no driver binds**:
with the bring-up sensors linked into the camss graph it never registered `/dev/media0` or any
`/dev/v4l-subdev*`, so `debug/9007` now describes the sensors on CCI without linking them. And
**without an IOMMU the VFE can overrun a buffer**: `video_buf_init()` hands the VFE only
`sg_dma_address(sgt->sgl)`, the first segment, and the VFE writes the whole plane from there.
`debug/9009` refuses any plane that is not exactly one DMA segment. It has been seen to fire -
a 640x480 frame came back as 4 segments, the kernel logged "plane 0 is 4 DMA segments, not 1:
refusing it", and REQBUFS failed cleanly. 64x32 SBGGR8 is 2 KB, one page, so it passes.

**Full sensor resolutions work since r159 (2026-10-04).** `debug/9010` gives camss contiguous
CMA buffers (`vb2_dma_contig`) whenever the device has no IOMMU, and leaves the dma-sg path -
with `9009`'s guard - for when one exists. CMA is 256 MB (`CONFIG_DMA_CMA=y`). Every size came
back exact with the alternating pattern, the 64x32 regression included:

        640x480     921600 bytes      half aa, half 55     (refused by 9009 before)
        1976x1200   7113600 bytes     half aa, half 55     the front sensor's size
        5248x3936   61968384 bytes    30984192 aa + 30984192 55, and all-ff for pattern 4
                                      the rear sensor's size, ~20 MB per frame, no stray byte

Use `--stream-mmap=2` at the rear size; three or four 20 MB buffers is a lot of CMA. And do not
verify 62 MB files with `od | sort` on the phone - it takes over ten minutes; Python's
`collections.Counter` does it in seconds. The proper long-term route is still the CAMSS IOMMU
(downstream: two `msm-smmu-v1` instances at 0xfda44000 and 0xfda64000).

**Those captures exposed a real GPU bug - fixed by `0089`, and it has nothing to do with the
camera.** The first full-size run oopsed `kswapd0`:

        Unable to handle kernel NULL pointer dereference at virtual address 00000014
        PC is at msm_gem_purge+0x100/0x15c     Comm: kswapd0

`msm_gem_purge()` ends with `shmem_truncate_range(file_inode(obj->filp), ...)` unconditionally,
and `is_purgeable()` never asks whether the object has a shmem file. This port runs the GPU
from the VRAM carveout - no GPU IOMMU in the build - and carveout objects are made with
`drm_gem_private_object_init()`, so `obj->filp` is NULL. In 6.16 `struct file` opens with
`f_lock, f_mode, f_op, f_mapping, private_data, f_inode`, which puts `f_inode` at exactly `0x14`
on 32-bit ARM - the faulting address. So the first time memory got tight while Mesa had a
`DONTNEED` buffer cached, the shrinker crashed inside kswapd, **killing background memory
reclaim for the rest of the boot** (`kswapd0` was gone afterwards). The 62 MB of capture
buffers only supplied the pressure; any heavy workload could do the same. `0089` returns early
when there is no `filp` - `put_pages()` has already handed the range back to the carveout.

Verified on r159: in one boot, **73 carveout objects (14 MB) went through the purge path with no
oops** - every GPU object here is a carveout one (`aspace=00000000` in
`/sys/kernel/debug/dri/0/gem`), and an object only counts as Purged once it has passed the point
where the old code dereferenced `filp`. The full-size captures were then repeated, exact, with
`kswapd0` still alive. A forced shrink through `/sys/kernel/debug/dri/0/shrink` was tried first
and is **not** evidence: it reported 0 purgeable objects, so it never reached the purge path.

**An unexplained stall, recorded and not attributed:** r157's first boot stopped logging 13 s
into userspace, while systemd was mounting `/boot`, with no panic, oops or watchdog message, and
the next boot came three minutes later. No camera module was loaded - all three are
blacklisted. Two further reboots of the same image were clean at ~72 s each. One occurrence, like
the single r126 reset, and pstore cannot say more.

**Both cameras, at a glance:**

        rear   Sony IMX200  module SOI20BS0  cci_i2c0 0x10  CSIPHY0 4-lane  MCLK0  AF: BU64296G
        front  Sony IMX132  module SEM02BN1  cci_i2c1 0x36  CSIPHY2 2-lane  MCLK2  no AF
2b. **DONE 2026-10-04 on r157: the capture path works, proven with the CSID's own test
   pattern - no sensor driver involved.** See "Test-pattern capture" below.
3. **Sensor drivers: IMX200 (rear) and IMX132 (front).** The long pole: neither has a
   mainline driver or a public datasheet, and the INCK has to be 19.2 MHz rather than the
   24 MHz most Sony register tables assume. IMX132 is the smaller, older part and the likelier
   first target. The downstream DT's
   per-module `pll` tables and the Sony camera driver's strings are the starting points. The
   AF actuator (BU64296G) and the EEPROM's calibration data come after the sensor streams.

Camera remains the largest area left, but step 1 is a weekend rather than a project, and
steps 1 and 2 together answer whether step 3 is worth starting.

### The rear sensor through CCS, 2026-10-04: it streams, and the CSI-2 data arrives corrupt

Both sensors are SMIA-family parts (IMX200 is SMIA++, model 0x0200; IMX132 is SMIA 1.0), so
`debug/9007` binds them to mainline's generic CCS driver (`compatible = "nokia,smia"`,
`CONFIG_VIDEO_CCS=m`) instead of borrowing imx219. The rear endpoint is linked to
`msm_csiphy0` - CCS needs a linked remote to read its endpoint at all. The front stays
unlinked: its PLL limits are broken (max PLL op 76 MHz against a 384 MHz minimum, op/vt limits
zero) and need their own quirk. Getting the rear one to stream took five driver fixes, each
found on the device:

- **`0091`** - the CCS-only limit registers (0x1138 clock_calculation, 0x1139/0x113a lane
  counts, 0x113b, 0x11b8/0x11b9, 0x1502, 0x1600) read back junk on Sony SMIA++ parts
  (`num_of_vt_lanes` = 129). Zero them for SMIA devices, and accept that a SMIA sensor has no
  PHY control to set.
- **`0092`** - in 6.16 only the source sub-device (the scaler) gets the driver's `init_state`
  hook, so the binner and pixel array kept 0x0 formats and every stream failed link
  validation with `-EPIPE` ("width does not match (source 0, sink 5248)").
- **`0093`** - the sub-device-state conversion also stopped the pixel array's format
  following its crop, and stopped a sink `set_format` storing the size, so no crop could
  ever validate. Old smiapp reported both from its crop rectangles.
- **`0094`** - IMX200 leaves the module ID block and the sensor manufacturer zero, so CCS's
  fallback to the sensor IDs never fired and no quirk could match. And its `op_sys_clk`
  limits (169-1100 MHz) are a per-lane bit rate, so it needs the lane-speed PLL model, as
  mainline's jt8ev1 quirk does. Without it CCS programmed op_sys = 768 MHz for a "96 MHz"
  link, four times what CSIPHY was told; the PHY threw ~480k error interrupts per stream.
- **`0095`** - camss's `video_start_streaming()` calls `s_stream` on every sub-device
  upstream of the video node, which includes the IMX200's binner. All CCS sub-devices share
  `ccs_set_stream`, so the sensor was started twice and its PLL rewritten while streaming;
  the sensor's I2C then wedged (CCI "master 0 queue 0 timeout" on 0x0308/0x0820). A kprobe
  trace of `ccs_write_addr` showed the second sequence starting right after `MODE_SELECT`.

Media-ctl recipe that validates (the sink formats now follow the crop):

        media-ctl -l '"msm_csiphy0":1->"msm_csid0":0[1],"msm_csid0":1->"msm_ispif0":0[1],"msm_ispif0":1->"msm_vfe0_rdi0":0[1]'
        media-ctl -V '"imx200 pixel_array 3-0010":0[crop:(0,0)/WxH]'
        media-ctl -V '"imx200 binner 3-0010":0[fmt:SRGGB12_1X12/WxH]'
        media-ctl -V '"imx200 scaler 3-0010":0[fmt:SRGGB12_1X12/WxH]'
        then SRGGB8_1X8/WxH on scaler:1, msm_csiphy0:0, msm_csid0:0, msm_ispif0:0, msm_vfe0_rdi0:0

**`0094` now counts all four lanes on the VT side too.** With `vt_lanes` = 1 only a 96 MHz link
passed the PLL check; with 4, links of 288-480 MHz pass at 8, 10 and 12 bit (576-960 Mbit/s per
lane), which is where the stock module table's per-mode lane rates sit (293-825 Mbit/s). CCS
picks the lowest, 288 MHz. 0x0820 (REQUESTED_LINK_RATE) stays as CCS writes it, the total over
all lanes - mainline's imx214 tables confirm Sony wants the total. `debug/9011` tried a per-lane
value and made things worse; it is out of the build and deleted.

What was measured on r171-r178, with Python reading `/dev/mem` mid-stream (no devmem applet on
the phone), live register writes, a kprobe on `ccs_write_addr` and `vfe_isr`'s dev_dbg:

- **RAW8 cannot work here.** In "RAW8" the sensor sends its lines as data type **0x30**
  (user-defined) with WC 5248 - read off the CSID's captured-header register 0x06c, whose
  layout is `DI[31:24] WC[23:8] ECC[7:0]` (it took a while to get that order right; ECC
  confirms it). CSID maps 0x2a, so every line was dropped. Use **RAW10** (`SRGGB10_1X10`,
  `pRAA`).
- **RAW10 delivers real pixels.** The first RAW10 capture came back the right size,
  5248 x 3936 x 10/8 per frame, and the bytes decode as RAW10 groups with the test pattern's
  exact bar values (green bar `00 ff 00 ff cc`). But each stored line held only ~58% of its
  bytes (an autocorrelation period of 3776 instead of 6560), spread evenly.
- **Settle 9 gives a clean link at 288 MHz; camss computes 11, which is marginal.** At 11
  the PHY raises ~12-40k error interrupts/s with bit 0x01/0x11 per lane, and on some boots
  0x10 (no sync); 13 and above never sync. At 9 the PHY goes nearly silent (~6/s), the CSID
  ECC counter (0x094, two 16-bit halves) stops moving, CRC errors stay at a fixed count,
  and ~100k packets/s arrive. The cliff wanders by a count or two between boots.
- **On the clean link nothing reaches the ISPIF or VFE**: no RDI SOF, no write-master done,
  only reset/halt acks, at every clock-lane settle from 0 to 255. Scanning the CSID's data
  type LUT through every long-packet type 0x10-0x3f live changed nothing either. The only
  runs that produced frames had a noisy link - the working theory is that the VFE starts a
  frame on a frame-start short packet that a clean link never delivers (or delivers on a
  channel CSID does not map), and that corrupted headers occasionally forged one. That would
  also explain the 58% lines. The embedded-data line that *is* captured is VC0 DT 0x12, so
  the sensor does use VC0. A write of 0 to SMIA's `csi_channel_identifier` (0x0110) changed
  nothing.
- `debug/9012` raises the msm8974 VFE clock (RDI sized at 16 bits a cycle) and the CSID
  clock (always 200 MHz). The 64-bit RDI assumption gave 37.5-50 MHz; neither change
  restored the missing 42% while frames were still coming only from noise, so both stay
  debug until a clean link delivers frames.
- Lane order and lane count are not the problem: one lane (`r170-1lane`) and PHY lanes 0
  and 4 swapped (`r171-swap`) were both tried. The CSID captured-header registers latch once
  per stream; `CORE_CTRL_1` bits did not make the others capture.

Next: find where frame starts go on a clean link - CSID short-packet handling (maybe the
sensor sends line start/end packets too: ~100k packets/s is ~3.6 per line), the ISPIF CID
mask and the VFE's RDI SOF source - and compare against the TPG, which streams at 20 fps
through the same CSID/ISPIF/VFE with the CSID status register reading 0 throughout.

**One stream per boot.** After a stream that times out, the next start fails with "VFE sof
timeout", and once reset the phone outright. Reboot between tests. The scripts used
(`treg.sh` with `rd.py`, `sweep*.py`, `hdr.py`, `cap2.py`, `dtscan.py`, `setsettle.py`, `an10.py`,
and `ttpg.sh` for the TPG) sit in `/home/mahan` on the phone. **Never read CSIPHY/CSID
registers through `/dev/mem` while their clocks are off** - `setsettle.py` waits for
`camss_csi0phy_clk` to be enabled first; `rd.py` once read 0xff from a powered-down PHY.

### First image, 2026-10-04 evening: the stock firmware's init table was the missing piece

The stock FTF (`D5503_14.6.A.1.236_*.zip`) holds the camera
configuration in `/system/vendor/camera/SOI20BS0_IMX200.dat` (and `SEM02BN1_IMX132.dat` for
the front). `tools/unsin.py` unpacks `system.sin` (SIN v3: an MMCF map of ADDR records) to an
ext4 image that `debugfs -R "rdump / dir"` reads without mounting; `tools/semcdat.py` dumps the
module file's register tables - 12-byte entries `u32 addr, u32 value, u32 0xffff0000`:

- an **87-register init table** of Sony manufacturer registers (0x3xxx/0x5xxx/0x9xxx) plus
  0x0105=01, 0x0110=00, 0x0220=01 - CCS writes none of it;
- **18 per-mode tables** of 130 registers (mode 0 is 5248x3936 RAW10). They set the lane
  count at **0x0108=03** (the older Sony location; stock never writes 0x0114), manual D-PHY
  timings at 0x0830-0x0847, and more manufacturer registers - but **no PLL registers**;
- small tables for stream on/off, soft reset, orientation (0x0101=03) and test pattern
  (0x0601). The header before the tables holds per-mode geometry (crop, output size, binning,
  frame length 3992, line length 5904 in every mode).

`debug/9013` writes them from the IMX200 quirk's `post_poweron`, selected by a debug module
parameter `imx200_stock` (1 init table, 2 the 0x0108 lane write, 4 the rest of mode 0). That
needed **`0096`**: `ccs_write_addr_8s()` - the helper every CCS quirk table goes through - passed
bare 16-bit addresses to `ccs_write_addr()`, which since the CCI conversion wants the width
encoded, so every quirk table write failed with -EINVAL ("invalid reg-width 0").

**Init table only (`imx200_stock=1`), RAW10, 288 MHz link, CSIPHY settle 3: clean frames.**
The settle sweep with the init table loaded: at 3 the VFE gets ~15k interrupts/s and the CSID
ECC counter does not move; at 7 and 9 the link is just as clean but the VFE gets nothing; at
11 (camss's own value) sync fails. The reading is that the frame-start short packets come in
bursts whose HS-zero is shorter than the line bursts', and only a short settle catches them.
The sensor's colour bars came back perfect - the autocorrelation period is exactly 13120 bytes,
two 6560-byte lines - and with the test pattern off, exposure 3000 lines and analogue gain 128,
**a real photo of the room**: dim, raw (no lens shading), and wrapped about two thirds down
(the frame in the buffer starts mid-image, with a horizontal offset).

All of mode 0 on top of the init table (`imx200_stock=7`) moves the sync window down to settle
1 with ECC errors - those tables change the D-PHY timing, maybe the rate - so they stay off for
now. The `pll` array in the stock DT (600, 318, ... per mode) is the per-mode lane rate; where
stock programs the PLL itself is still unknown (not in the .dat tables).

**The phone hung once** (USB gadget dead, no oops, needed Power+VolUp) during a settle sweep
with the init table loaded. A gentler sweep (3-11) on the next boot was fine.

Next: find why the frame lands wrapped (frame start vs. the VFE write start, maybe the first
frames after start), then fold the init table into the quirk properly, make camss's settle
right for this sensor, and take a correctly exposed photo. Then the IMX132 the same way.

### Second image, 2026-10-04 late: aligned, upright, and seeing the scene

Three more findings, each on the device, with `debug/9013`'s `imx200_stock` bits now split
into groups (1 init, 2 lane write, 4 mode-0 rest, 8 mode-0 sizes, 16 mode-0 clock regs
0x3004/0x3005/0x9229, 32 mode-0 D-PHY timings):

- **The ribbon shift was missed frame starts, and settle 2 fixes it.** At settle 3 every
  other frame started at the wrong place (the fade test pattern shows it: even frames have the
  bar edge at x = 1311 from row 0, odd ones are offset). At settle 2 and at 1, 8 of 8 frames
  are aligned. (The pattern's own gradient repeats every 2048 rows - that is not a frame edge.)
- **The pixel array read black until the stock size registers went in.** With the init table
  alone the image sat at the black level (64) however long the exposure - the sensor was
  reading somewhere dark. Mode 0's size/crop registers (0x13c0-0x13c4, 0xad34-0xad3f,
  0x9030-0x9037; `imx200_stock=9`) put real light on it: a full, aligned frame of the desk.
- **Read the sensor back before believing a register.** `i2ctransfer -f -y 3` on the phone
  (i2c-tools installed; /dev/i2c-3 is CCI master 0) reads the IMX200 mid-stream. It showed
  exposure and gain set as asked, 0x0108 already 3 (4 lanes) by default, 0x0114 reading 0, and
  CCS's PLL actually at 19.2 / 6 x 108 = 345.6 MHz.
- The mode-0 clock group (16) changes the sensor's lane timing so that no settle value syncs
  cleanly; it stays off. The stock kernel (unpacked: SIN -> ELF -> LZO zImage) only does power,
  EEPROM and module info - sensor registers come from Sony's userspace, so where stock sets the
  PLL is still open.

Working recipe now: `imx200_stock=9`, RAW10, 288 MHz, settle 2, exposure up to 3976 lines,
analogue gain e.g. 128; rotate the result 90 degrees clockwise. Still to do: lens shading and
colour, brightness/exposure units, folding all this into real patches (init + size tables in
the quirk, settle in camss), then the IMX132.

## Parked patches

Out of the build, kept because the data in them was expensive to recover:

- `0082` - the actual SoC collapse in `spm_suspend_enter()`. Correct-looking and
  **the phone does not wake from it** (r135, Phase 2). Parked rather than deleted
  because the sequence is probably right and the wakeup side is the suspect, so
  whatever fixes the wakeup will want this back unchanged. r135 is safe to run but
  must never be sent to `deep`.
- `0078` - dropping `cold_boot_done` so the ACC/SAW release re-runs on every
  online, plus a non-returning `qcom_cpu_die()`. **Parked because it is actively
  dangerous**, not merely incomplete: it hard-resets the SoC at the online, every
  time, by clamping and resetting a core that is still powered. Kept because the
  diagnosis in it is right (see Phase 2) and because the next attempt needs exactly
  this plus a prior power collapse. Do not re-add it on its own.
- `0077` - the `platform_suspend_ops`. Correct as far as it goes, and parked only
  because `PM_SUSPEND_MEM` parks the secondary CPUs and this SoC cannot bring them
  back. Note it is not inert if re-added: registering any suspend ops makes `deep`
  the **default** `mem_sleep`, so ordinary idle suspends take that path too.
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
- **The battery thermistor now reports a temperature (`0069`).** It was declared
  `VADC_CHAN_NO_SCALE(LR_MUX1_BAT_THERM, 0)`, so it appeared as
  `in_voltage48_raw` with no `_input` and nothing could read a battery
  temperature. Mainline has no `SCALE_BATT_THERM`; of the tables it does carry,
  `SCALE_THERM_100K_PULLUP` is the closest, and on this phone it lands sensibly:

        in_temp48_label   LR_MUX1_BAT_THERM
        in_temp48_input   39120      (39.1 C)
        DIE_TEMP          45735      (45.7 C, same moment)

  624mV on the channel, which the 100k table puts at 39C, against a PMIC die at
  45.7C - a battery a few degrees under the die is what you would expect. The
  scale function is chosen **in the driver**, not from DT (`prop.scale_fn_type =
  vadc_chans[prop.channel].scale_fn_type`), so this is a driver patch and needs
  no reflash. RAW is still exposed, so the millivolts remain available.

  **Treat it as indicative, not calibrated** - it is the generic 100k curve, not
  this battery's own table. But it does genuinely *track*, which was checked
  rather than assumed (2026-09-19, five minutes of four-core load then cooldown,
  sampled every 30s):

        base   39.29 -> 39.34 C   die 45.69 -> 45.49    flat
        LOAD   39.34 -> 40.96 C   die 45.49 -> 51.14    monotonic, every sample
        cool   40.96 -> 41.14 C   die 51.14 -> 49.15    still RISING
               41.14 -> 40.78 C   die       -> 47.73    then decaying slowly

  Three things there are hard to fake. The baseline is flat to 0.05C, so the
  channel is not drifting or noisy. The load ramp is monotonic on every single
  sample, +1.62C of battery against +5.65C of die - about 29%, which is the right
  order for a cell against an SoC die rather than the 1:1 you would see if this
  were secretly reading the die. And on cooldown the **battery keeps rising for
  60-90s after the load stops**, peaking at 41.14C while the die has already
  dropped 2C, then decays slowly. That lag is the signature of a large thermal
  mass, and neither a stuck reading nor a mislabelled channel produces it.

  What is still unverified is the *absolute* calibration - a cold reference would
  need the phone put somewhere cold, which nobody has done.

  Note this does **not** give `qcom_smbb` a `temp` property: that driver only
  reads the PMIC's BTC comparator for health and has no
  `POWER_SUPPLY_PROP_TEMP`. `/sys/class/power_supply/smbb-bif` still has no
  `temp`. Wiring one up means a driver change plus an `io-channels` entry in DT,
  and the DT half would need a flash.

- **The charger now reports that temperature too (`0070`, `0071`).**
  `qcom_smbb` gained `POWER_SUPPLY_PROP_TEMP`, reading a `batt-therm` IIO
  channel looked up lazily on first use exactly as `vbat` is, and the DT hands
  it `VADC_LR_MUX1_BAT_THERM`. Verified end to end on r119:

        iio in_temp48_input          35714 m C
        smbb-bif/temp                  357        (tenths, so 35.7 C)
        upower temperature            35.7 degrees C

  Two unit traps in that path, both live in `smbb_battery_temp()`: IIO processed
  temperature is milli-degrees while `POWER_SUPPLY_PROP_TEMP` is **tenths**,
  hence the `/100`; and `iio_read_channel_processed()` returns `IIO_VAL_INT` on
  success rather than 0, so only a negative is an error - the same quirk that
  bit the fuel gauge.

  `CONFIG_CHARGER_QCOM_SMBB=y`, so the driver half needs a flash as much as the
  DT half does; one flash covered both.

  **This is the change the USB trap warns about, and it was safe only because
  the mitigation was already there.** Adding `io-channels` to `&smbb` is what
  once killed USB through fw_devlink. The new channel comes from the *same*
  provider as the existing `vbat` one, and `post-init-providers =
  <&pm8941_vadc>` was already on the node, so the edge stays cleared. Confirmed
  in the built DTB rather than the patch text - `charger@1000` shows
  `io-channels = 0xa5:0x06, 0xa5:0x30` with one provider - and confirmed again
  after the flash by `/sys/class/udc/ci_hdrc.0` still existing. **Anything that
  adds a phandle from `&smbb` to a different provider still needs its own
  `post-init-providers` entry.**

- **WiFi power save retested 2026-09-19, and it still cannot be enabled.** The
  31 mA WCNSS costs makes this worth one attempt, and the answer is unchanged
  from 2026-09-09 - `0008` did not help:

        309.37  wlan0: associated                   <- association succeeds
        320.37  Timeout! No SMD response to req 78  <- hal_enter_bmps, FIRST failure
        320.38  Can not enter BMPS!
        340.86+ every later request times out       <- firmware wedged for good

  `hal_enter_bmps` is the first thing to fail, and after it the firmware answers
  nothing: `hal_set_link_st`, `hal_switch_channel`, `hal_enter_imps`,
  `hal_delete_sta_self` and `hal_stop` each burn their full 10s timeout. Only a
  reboot recovers WiFi. The 31 mA stays.

  **Two traps if anyone retries.** NetworkManager stores power save *per
  connection*, in `/etc/NetworkManager/system-connections/<name>.nmconnection`
  as `powersave=3`, and that overrides the global `conf.d` file - so one attempt
  wedges WiFi on **every subsequent boot** until the profile is edited back.
  And `nmcli` cannot undo it once things are wedged, because NM dies with the
  device; the revert is a `sed` on the file plus a reboot.

  The thing to investigate, if it is ever worth another wedge-and-reboot cycle,
  is why the firmware never answers `ENTER_BMPS`.
  `wcn36xx_smd_enter_bmps()` sends `msg_body.tbtt = vif->bss_conf.sync_tsf` and
  `msg_body.dtim_period = vif_priv->dtim_period`; a zero or stale value in
  either is the usual cause.

- **Trap: unloading `qcom_spmi_vadc` powers the phone off.** It is `=m`, so a
  reload looks like the cheap way to test a VADC change. It is not. The module is
  the capacity source behind `/sys/class/power_supply/smbb-bif`, and while it is
  gone UPower sees 0% with `warning-level: action` and performs its critical
  action, which is now PowerOff - the old `CriticalPowerAction=Ignore` workaround
  was removed once the fuel gauge became real (see
  [[xperia-z1c-power-shutdown]]). The phone shut down cleanly about two minutes
  after a `modprobe -r qcom_spmi_vadc`, on a battery reading 4.30V, and had to be
  powered back on by hand. **Reboot to pick up a VADC change, or stop upower
  first.**

- `THERMAL_EMULATION` is still enabled. It is how the thermal trips were tested, and
  it also lets root feed the thermal core a fake low reading. Worth dropping once the
  frequency ceiling can reach 75 C honestly.
