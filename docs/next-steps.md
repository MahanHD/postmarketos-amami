# Next steps

Rewritten 2026-09-12, after a long session that fixed a core-wedging bug of our own
making, produced the first power numbers, and then solved the GPU IOMMU.

The headline change since the last version: **the GPU IOMMU works**, and the thing
that cracked it was not another build. Five rebuild-and-guess cycles had failed;
reading the SMMU's own registers on a running phone through `/dev/mem` found both
bugs in one sitting. Prefer instrumenting the hardware over rebuilding it.

## Where the port stands

Working: panel, touch, Xfce on freedreno, WiFi, Bluetooth, charging (on a real
supply), battery percentage, USB networking, sensors bar proximity, the notification
LED, suspend (s2idle), GPU and CPU frequency scaling, and CPU thermal throttling.

Not working: audio, proximity, ambient light, deep suspend.

Both IOMMUs work as of `0034`-`0037`, and the 192MB carveout can be reclaimed, but
they are **in the build as of r76** and the 192MB carveout is gone; see below.

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

### The GPU IOMMU: solved, and in the build

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

It cost throughput, measured like-for-like at
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

That was the trade: 192MB of RAM against about 2.7x of GPU throughput, on a 2GB device
whose heaviest graphics load is an Xfce desktop. **The memory won.** `0034` through
`0037` are in the build as of r76, flashed and verified across a real reboot -
`MemAvailable` 1395404 kB against 1217868 kB, about 172MB more, with CMA entirely free
and zero faults under load.

Needs `CONFIG_ARM_SMMU_DISABLE_BYPASS_BY_DEFAULT` **off in the config**, not on the
command line: `boot-deploy` rewrites the command line, and undescribed MDSS masters
losing bypass means a dark panel.

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

**The biggest remaining lever on this phone**, bigger than the IOMMU. It is why idle
costs 252 mA and why there is no standby to speak of: cores collapse individually
while the SoC never does, so the RPM stays up, rails stay put and DDR stays refreshed.

It is unimplemented, not unconfigured. Nothing in mainline calls `suspend_set_ops()`
with `PM_SUSPEND_MEM` for Qualcomm ARM32 - there is no such call under
`drivers/soc/qcom`, `drivers/firmware` or `arch/arm/mach-qcom`, and that directory
holds only `Kconfig`, `Makefile` and `platsmp.c`. `ARM_PSCI` is off, so there is no
firmware route either.

Scope it by reading how arm64 Qualcomm gets there through PSCI, and what downstream
msm8974 does instead. Then platform suspend ops, SPM programming for system-wide
power collapse rather than the per-core standalone kind, and RPM coordination.

## Phase 3: audio

Unchanged and still the largest untouched area: no APR/SLIMbus device tree, no WCD9320
codec driver. The DSP boots and every sensor on it works, so the groundwork exists.

## Parked patches

Out of the build, kept because the data in them was expensive to recover:

- `0018`, `0025` - the earlier `qcom_iommu` node and the GPU's binding to it,
  superseded by `0034`-`0037` but kept for the device-tree data in them.
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
- `BAT_THERM` sits at 642 mV, close enough to the limit that the narrow jeita band
  rejected it. It works with the extended band, but *why* a normal reading lands that
  near the edge is not understood, and that matters before trusting the charger in the
  cold.
- `THERMAL_EMULATION` is still enabled. It is how the thermal trips were tested, and
  it also lets root feed the thermal core a fake low reading. Worth dropping once the
  frequency ceiling can reach 75 C honestly.
