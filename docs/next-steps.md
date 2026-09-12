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

The GPU IOMMU works as of `0034`/`0035` but is out of the build; see below.

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
  visible. Global fault is SPI 37, not 38 (38 is the secure line, which is what
  downstream lists); context banks take one line each from 241 up, not 241 three
  times. Getting this wrong is silent - FSR latches, the transaction is terminated,
  and a faulting GPU looks like an idle one.

**It stays out of the build**, and now for a measured reason. Like-for-like at
320MHz, `vblank_mode=0`: 780 FPS on the carveout kernel against 154 FPS behind the
SMMU, both with zero hangchecks. Five times the cost, and it reclaims nothing until
the **MDP** has an IOMMU, because `msm_use_mmu()` tests the display controller.

Worth doing before turning it on: find where the five-fold cost goes. The suspects -
non-coherent page-table walks, TLB maintenance on every map and unmap, a runtime-PM
round trip per operation - are all unmeasured. And `msm8974_smmu_write_s2cr` forces
`NSCFG`/`MEMATTR` on a theory that later proved wrong; it has never been tested on
its own.

The technique is the reusable part. `CONFIG_STRICT_DEVMEM` is off, so `/dev/mem`
reaches any register block directly - but pin its runtime PM first
(`echo on > /sys/bus/platform/devices/<dev>/power/control`) or the read hangs the
bus on an unclocked block. Fault injection plus a scan of the GIC's pending-and-
disabled set is how both interrupt numbers were recovered without a vendor tree.

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

- `0034`, `0035` - the working GPU IOMMU, held back on throughput cost.
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
- `BAT_THERM` sits at 642 mV, close enough to the limit that the narrow jeita band
  rejected it. It works with the extended band, but *why* a normal reading lands that
  near the edge is not understood, and that matters before trusting the charger in the
  cold.
- `THERMAL_EMULATION` is still enabled. It is how the thermal trips were tested, and
  it also lets root feed the thermal core a fake low reading. Worth dropping once the
  frequency ceiling can reach 75 C honestly.
