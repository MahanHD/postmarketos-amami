# Next steps

Rewritten 2026-09-12, after a long session that fixed a core-wedging bug of our own
making, produced the first power numbers, and ruled out five plausible explanations
for two problems that remain open.

The headline change since the last version: **stop building for a while.** Both live
threads have converged on needing a source rather than another cycle, and the cost of
guessing has been measured — five dead ends, one build each.

## Where the port stands

Working: panel, touch, Xfce on freedreno, WiFi, Bluetooth, charging (on a real
supply), battery percentage, USB networking, sensors bar proximity, the notification
LED, suspend (s2idle), GPU and CPU frequency scaling, and CPU thermal throttling.

Not working: audio, proximity, ambient light, deep suspend, the GPU IOMMU.

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

Both open problems need an external source. Produce a written finding first; no
flashing until there is one.

### Why the GPU will not idle behind its IOMMU

Everything in software now works - the IOMMU probes, the GPU attaches, the domain
allocates, the address space is built (`0026` fixed the `-EBUSY`, which was the ARM32
DMA glue claiming the group first). Then `a3xx_hw_init` reports `timeout waiting for
GPU to idle!` and `adreno_load_gpu` fails with `-22`.

Already ruled out, do not repeat: OCMEM contention (`active=0x0`, allocates cleanly);
mainline's `0xffffffff` write to 0x2000 secretly halting the IOMMU (skipping it
changed nothing); the missing non-secure BFB init (`applied 12 bfb settings`, failed
identically).

Where to look: downstream `msm_iommu-v1.c` for what those registers actually mean -
the prior art's claim that 0x2000 is `MICRO_MMU_CTRL` is **contradicted by
experiment**, so its offsets and its BFB table are both suspect; how kgsl sets up its
context banks and what it expects of the aperture; Matti Lehtimäki's
`qcom-msm8974-5.19.y-iommu` read commit by commit rather than skimmed.

Not yet eliminated: whether `iommus` should name one context bank rather than two,
and whether faults are being raised but never reported.

**Note the payoff is smaller than it looks.** `msm_use_mmu()` tests the *display*
controller and its parent, not the GPU, so the 192 MB carveout only goes away once the
**MDP** has an IOMMU. A flawless GPU IOMMU reclaims nothing by itself.

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

- `0018`, `0025` - the GPU IOMMU node and the GPU's binding to it.
- `0027` - the non-secure BFB settings.
- `0031` - subscribing to every data type, a prerequisite for ambient light.

In the build but inert without those: `0017` (optional secure id), `0019` (the `alt`
clock, which is what stopped the first attempt hanging the phone), `0026` (detaching
the ARM DMA mapping).

**A kernel with the IOMMU bound is a regression** - the display still works but the
GPU falls back to `llvmpipe`. Check `glxinfo -B` reports `FD330` after touching any of
this, not merely that the screen lights up.

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
