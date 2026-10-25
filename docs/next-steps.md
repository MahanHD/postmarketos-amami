# Next steps

Where the port stands and what comes next, in order. The settled findings are in
`notes.md`, the history behind every item in `worklog.md`.

## Current state (2026-10-22)

The phone runs kernel 6.16.12 built from `recipe/` at pkgrel 258 (`uname -v` prints
`#259`), with boot image 258. The recipe applies exactly the patches in `patches/`; work
out of the build with a way back is in `patches/parked/`, diagnostics in
`patches/debug/`. There is no phone backup (`backups/README.md`).

Userspace from this repo: libcamera r8 (`recipe/libcamera`), Mesa r4 (`recipe/mesa`),
libdng r1, libmegapixels r2 and Megapixels r13 (`recipe/libdng`, `recipe/libmegapixels`,
`recipe/megapixels`), and the files in `userspace/` (see `building.md`).

The GPU runs behind its IOMMU since r204 (`0034`-`0036`); the display still uses the
VRAM carveout, and so do all GPU buffers, which are cleared on allocation (`0106`). The
carveout is 256 MB (`msm.vram=256m cma=320M` in `tools/mkbootimg.py`): a 20 MP capture
in Megapixels needs nearly all of 192 MB. `devcore-collect` (`tools/`) runs from boot
and saves any GPU hang dump; none but deliberately injected ones since the fixes.

Working: display, touch, GPU (GTK4's GL renderer included), WiFi, Bluetooth, charging
with stock's temperature derating (`0119`) and battery reporting, all sensors (on most boots, item 1), the notification LED, CPU frequency scaling to
1497.6 MHz and GPU frequency scaling with thermal limits, CPU hotplug, suspend
(s2idle), and the rear camera in GNOME Snapshot and Megapixels with correct colour.

Not working: audio (no sound; the codec stays off at boot, `userspace/amami-audio-off.conf`)
and the front camera (not started).

After a kernel change, install the package for modules and rebuild the boot image with
`tools/mkbootimg.py` for anything built in or in the device tree. Tests that run long
on the phone go through `sudo systemd-run`; a `nohup` over SSH dies with the session.

## How this port is done

Two rules for every part of it. Fix problems at the root, with the most reliable
solution, not with a quick workaround; a workaround is only a stopgap, labelled as one,
while the real fix is under way. And start from the other firmwares, above all stock:
reverse engineer them, then use what they yield, combine it, and improve on it where we
can.

## 1. Audio (unparked 2026-10-22)

The WCD9320 (Taiko) driver is in the series (`0049`-`0068`): the codec probes, every
register reads and writes, the card enumerates, the whole DAPM path powers up, and the
SLIMbus channel handshake completes. It is still silent. The one measured symptom: the
codec's SLIMbus RX port sits in permanent overflow for the whole of a playback, so data
arrives and the codec consumes none of it, and the same in the capture direction. Every
layer that can be read matches a working reference (both register spaces against
`golden-reference/`, the clock by substituting the internal RC oscillator, the supplies,
the bus transactions, the DSP port configuration and the rate maths).

The channel messages are compared now (2026-10-22, r242-r244): `CONNECT_SINK`,
`DEF_ACT_CHAN` and `RECONFIG_NOW` match downstream byte for byte after `0123` (the data
format bits), and streams are stopped as downstream stops them (`0124`-`0126`). The
overflow is unchanged from the first sample of a boot's first playback.

Measured live since (r245-r248, worklog 2026-10-22 "later"): the overflow is
continuous, not a latch; the interface device's per-port state byte goes `00 -> 42` at
the instant of `DEF_ACT_CHAN` + `RECONFIG_NOW`, every message is ACKed with success,
and re-activating later lands on `42` again; no port register moves it, even with the
port disabled. The TX side never activates (`0x95` stays `00`), and the handset mic set
up by hand (ADC1 -> DEC6 -> TX6, `0127`) captures exact zeros. The loudspeaker is
RX7 -> SPK DRV (eight golden registers), which the driver has no widgets for yet.

An ADSP restart with the codec loaded now survives (r252, `0128`-`0131`): it used to oops
or deadlock, because the restart re-registers the SLIMbus controller.
`0128`-`0131` were reviewed and revised on 2026-10-25 (r253, `review.md` pass 6).

Next: the state byte is the one thing that differs at the moment it goes wrong, and
nothing documents it. Find what writes or reports it: downstream's
`wcd9xxx-slimslave.c` and `slim-msm-ngd.c` for any per-port step between connect and
activate that this port does not do, and the ADSP-side channel state if it can be read.
Then the loudspeaker widgets (RX7, SPK DRV), so the first data that flows can be heard
with `tools/mic-level.py`.

Where it is written down: `worklog.md`, "Phase 3: audio" (the latest state and this
lead at "Where that leaves it", then the two leads closed on 2026-10-01); `notes.md`,
"Audio". The codec stays off at boot (`userspace/amami-audio-off.conf`); for audio
work load it by hand, and `0065`/`0066` make it reloadable without a reboot. The PM8941
GPIO 15 MCLK pin mux is a known defect (review pass 3, finding 9), proven not to be the
cause. The audio patches were reviewed in pass 6 (`review.md`).

## 2. Sensors missing on some boots (solved 2026-10-25)

`0132`: the ADSP's sensor I2C pins (GPIO 87/88) were left by the bootloader as GPIO
outputs driven low, so the first sensor it probed failed on every cold start and the
sensors only came up after a restart. Five boots on r257: no ADSP fault, all four
sensors on the first run. The bad recovery that could leave SLIMbus without QMI went
with it, since there is no recovery at boot any more. `worklog.md`, "The ADSP's first
run, solved".

## 3. After the review

All six review passes are done (`review.md`), audio as pass 6. Passes 3 and 4 left a list for upstreaming, not for this phone:
shared-dtsi changes that need other boards' configs or voltages (MPM routing, the
unvolted OPPs, the GPU SMMU), `0036`'s page alignment derived from the domain instead of
fixed, and bindings for the new compatibles and properties. Pass 5 left pstore and
`THERMAL_EMULATION` to switch off with the next kernel change.

The charger's return from warm to normal derating (below 43C) has not been seen on the
phone yet, only the switch to warm; `dmesg` logs "normal charging" when it happens.

## 4. Camera, rear (IMX200)

1. **A failed stream start wedges camss** until reboot (every later start returns
   EINVAL). Seen after a CCI timeout writing the lens position; the notes record the
   same after any failed or timed-out start. Recovery after a failed start is unwritten.
2. **A cheap preview.** Megapixels previews at 2624x1976 and keeps about 7 of the 30
   frames a second. Its processing thread takes 80% of a core, a quarter of it copying
   each frame out of the uncached camera buffer and much of the rest page faults on the
   fresh copy. Cached buffers (`V4L2_MEMORY_FLAG_NON_COHERENT`) would make that copy
   cheap, but dma-direct's non-coherent allocation refuses highmem pages, and the CMA
   area is in highmem.
3. **Photo development** takes about 70 s on an idle phone (`dcraw_emu` 29 s with FBDD
   denoising, ImageMagick 35 s, exiftool 5 s), and about twice that with the preview
   open, for the same reason as item 2.
4. **Full-size frames in libcamera apps.** The software ISP crops a few pixels (5248
   wide gives 5240), so asking for 2624x1976 already picks the 5248x3936 mode, and its
   four 26 MB buffers do not fit in CMA next to the carveout (`cam` fails with "Wanted
   4, got 2"). Snapshot takes its photos from the 1920x1080 preview. A GPU debayer
   needs an msm IOMMU for the display first.
5. **The first frames of a stream** come out at full size, half switched or at the
   default exposure: stream-on reloads the readout registers, and the clock presets
   that would keep them (0x3004-0x3005) are made for stock's 8 MHz clock. camss drops
   the first eight, `0116` bounds any oversized frame, and the writes after stream-on
   end about 120 ms in. An 8 MHz MCLK (M/N, which `0090` removed because it came out
   wrong) would let the sensor run stock's tables as they are, 4x4 modes included.
6. **Autofocus.** Continuous contrast AF works (`recipe/libcamera` `0007`). It rescans
   on large sharpness changes only; tap to focus and the AF controls for apps are not
   there yet, and a scan takes a few seconds.
7. **Tuning.** White balance and exposure in libcamera are its simple defaults. The
   EEPROM's remaining bytes and stock's `exposure_ctrl.dat` may hold better starting
   points.

## 5. CPU above 1.5 GHz

`0112` runs the cores to 1497.6 MHz: VDD_APC (pm8841 s5, SID 5) sits at 900 mV, which
covers this bin's PVS voltage up to 1497.6 MHz (895 mV). The chip is rated to 2150.4
MHz at 1 V, and the rest needs Linux to set the rail. Stock does it through the L2 SAW
(`msm_spm_set_vdd()`), so the route is mainline's `qcom,saw-reg` support in
`qcom_spmi-regulator` with s5 as the SAW leader; check what SAW version that code
expects against the L2 SAW here (0x20010000 at +0xfd0, SAW2 v2.1) before trusting it.
Then widen s5's constraints and add the OPPs above 1497.6 MHz. Thermal already
throttles four loaded cores at 1.5 GHz near 75 C, so sustained gains are modest;
single-thread bursts gain most.

## 6. GPU

1. kgsl escalates to a full stop and start when a soft reset fails; drm does not. No
   case of it has been seen, and `devcore-collect` would catch one.
2. The other a3xx workarounds stock applies on this chip (flag bits in `notes.md`) did
   not affect the hang. Port one only if a symptom points to it.
3. `0105` (kgsl's power-on fixup) is parked; retry it on top of `0111` only if shader
   corruption after a power-on shows up.
4. Offer the Mesa fix upstream once the port is clean.
5. `oxili_gfx3d_clk status stuck at 'off'` at the GPU's first power-up, then a
   disable of an already disabled clock: 3 boots of 25 (`review.md`, pass 4). The GPU
   works afterwards. Count it over more boots before chasing it.

## 7. Camera, front (IMX132)

Same method as the rear: its stock file is `SEM02BN1_IMX132.dat`. Its CCS limits are
broken (PLL op minimum above maximum), so it needs a quirk of its own first; the CCS
fixes parked in `patches/parked/` and `patches/debug/9007` are the starting point.

## Later

- The display IOMMU (`patches/parked/0037`, `0038`), which would free the 256 MB
  carveout; the panel goes black, and the open question is in `notes.md`.
- The CAMSS IOMMU, which would let CAMSS use scattered buffers.
- Small cleanups: `THERMAL_EMULATION`, the leftover half of the CPU wedge work, the
  cosmetic 307200 kHz warning, and `/boot` mounting as an unchecked filesystem.

## Working rules on this phone

- Power off is Power + Volume Up. Plugged in, it switches itself back on.
- Fastboot: hold Volume Up while plugging in, flash, then `fastboot reboot`.
- Run anything risky detached (`systemd-run`) and log to persistent storage with
  `sync` after each line; `/run` and `/tmp` do not survive the reset you are
  debugging.
- Never read camss registers through `/dev/mem` while their clocks are off.
- `pstore` is empty here even after a clean reboot; do not reason from its
  emptiness.
