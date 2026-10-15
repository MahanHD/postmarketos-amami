# Next steps

Where the port stands and what comes next, in order. The history behind every item
is in `worklog.md`; the settled findings are in `notes.md`.

## Current state (2026-10-15)

The phone runs kernel 6.16.12 built from `recipe/` at pkgrel 226, with the boot image
from 222 (`uname -v` prints `#223`; nothing built in or in the device tree changed since). `0105` (kgsl's power-on fixup) stays parked (GPU
item 2). There is no phone backup (`backups/README.md`). Userspace
from this repo: libcamera r8 (`recipe/libcamera`), Mesa r4 (`recipe/mesa`), libdng r1,
libmegapixels r2 and Megapixels r6 (`recipe/libdng`, `recipe/libmegapixels`,
`recipe/megapixels`), with
`userspace/megapixels/*` in `/usr/share/megapixels/config/`. The GPU runs behind its
IOMMU since r204 (`0034`-`0036`); the display still uses the VRAM carveout, and so do all
GPU buffers, which are cleared on allocation since r206 (`0106`). Install the package for module changes and rebuild the boot image with
`tools/mkbootimg.py` for anything built in or in the device tree.

Working: display, touch, GPU (GTK4's GL renderer included), WiFi, Bluetooth, charging and
battery reporting, all sensors, the notification LED, CPU and GPU frequency scaling with
thermal limits, CPU hotplug, and suspend (s2idle). The rear camera works in Snapshot and
in Megapixels, with correct colour.

Not working: audio (no sound, see `notes.md`) and the front camera (not started).

The camera loads at boot and works in GNOME Snapshot through libcamera and PipeWire, and
in Megapixels. `capture.sh` still works for raw frames; at night it needs `VBLANK=30000`,
a long exposure and gain 240, or the frame is black.

**Review in progress:** `review.md` holds a pass-by-pass review of the whole port; passes 1
(GPU) and 2 (camera) are done, pass 3 (device tree) is next.

**Where to pick up:** the GPU power-on hang is fixed (`0111`, item 4: two hour-long
soaks on r214 with 0 hangs, against 3 to 9 before) and the CPU runs to 1.5 GHz
(`0112`). Next: the CPU rail through the SAW for the rest of the ladder, a pipeline
hang injector for GPU recovery, and the camera list. Tests that
run long on the phone go through `sudo systemd-run`; a `nohup` over SSH is killed when
the session closes.

## How this port is done

Two rules for every part of it. Fix problems at the root, with the most reliable
solution, not with a quick workaround; a workaround is only a stopgap, labelled as one,
while the real fix is under way. And start from the other firmwares, above all stock:
reverse engineer them, then use what they yield, combine it, and improve on it where we
can.

## GPU (Adreno 330)

The GTK4 hang is fixed (`notes.md`, "The GPU hang, solved"): Mesa now ends every direct
`CP_LOAD_STATE` with a register write, as the stock driver does
(`recipe/mesa`, r4). Megapixels and Snapshot run on GTK's GL renderer with no hangs, and
Snapshot's cairo stopgap is gone.

1. The other a3xx workarounds stock applies on this chip (flag bits in `notes.md`) did not
   affect the hang. They stay documented; port one only if a symptom points to it.
2. kgsl's power-on fixup is ported as `0105` and parked. Its commands are identical to
   the stock kernel's (`tools/re/kgsl-fixup-emu.py`) and it executes, but every version
   tried made the hangs no better or worse. Those hangs were the missing reset (item 4),
   so the fixup was never tested against the problem it is for. Retry it on top of
   `0111` only if shader corruption after a power-on shows up.
3. Carveout buffers are cleared on allocation since r206 (`0106`); that removed the
   "Division by zero" warnings and the cross-process data leak.
4. The hang on the first job after a power-on (3 to 9 an hour under
   `tools/gpu-soak.sh`) is the GPU coming back from runtime suspend *without* a power
   collapse: the GDSCs stay on while the SMMU, which shares them, is busy, and drm
   restarted the core without resetting it. kgsl resets it in that case. `0111` resets
   it at the start of every hw_init. Pinning the SMMU on forces the case: 22 hangs in 5
   cycles on r212, 0 in 10 on r214. This also explains why 5943 power-ons under
   `tools/gpu-pwron-stress.py` never hung: with no buffer maps the SMMU always suspended
   and the GDSCs always collapsed. `0107`-`0110` (error IRQs, kgsl framing, memory
   retention, BFB) did not change the rate and stay because stock does the same.
   Worklog: "GPU hangs overnight".
5. "GPU recovery fails for good" was the msm shrinker evicting VRAM carveout buffers and
   losing their contents, fixed by `0113` (r218; worklog, "Found: the shrinker emptied
   Xorg's buffers"). `devcore-collect` keeps running from boot. Left from the hunt:
   kgsl escalates to a full stop and start when a soft reset fails, drm does not; no
   case of that has been seen yet.
6. Offer the Mesa fix upstream once the port is clean.

## Camera, rear (IMX200)

1. **Megapixels** (`userspace/megapixels/sony,xperia-amami.conf`, `recipe/megapixels`):
   it previews live on the GPU, white is white, and auto exposure now has the whole 30 fps
   frame (`recipe/libmegapixels`). Clipped highlights stay white since r3
   (`clip-after-white-balance.patch`).
2. **Autofocus tuning.** Continuous contrast AF works (`recipe/libcamera` `0007`). It
   rescans on large sharpness changes only; tap to focus and the AF controls for apps
   are not there yet, and a scan takes a few seconds.
3. **Full-resolution photos from apps** need a GPU debayer (Megapixels does its own; the
   libcamera one still needs an msm IOMMU for the display), and enough CMA for the
   capture buffers.
4. **Tuning.** White balance and exposure are libcamera's simple defaults. The EEPROM's
   remaining bytes and stock's `exposure_ctrl.dat` may hold better starting points.
5. **The first binned frames** still come out at full size: stream-on reloads the
   readout registers, and the clock presets that would keep them (0x3004-0x3005) are made
   for stock's 8 MHz clock (review pass 2). `0116` stops the VFE writing them past the
   buffer. Making 8 MHz (an M/N MCLK, which `0090` removed because it came out wrong)
   would let the sensor run stock's tables as they are, 4x4 modes included.
6. **A cheap preview mode.** The 1312x988 mode is gone (it never delivered 1312-pixel
   lines), so previews run at 2624 wide and Megapixels' auto exposure takes about a
   minute to settle at night, dropping frames on the way.

## CPU above 1.5 GHz

`0112` (r216) runs the cores to 1497.6 MHz: VDD_APC (pm8841 s5, SID 5) is readable and
sits at 900 mV, which covers this bin's PVS voltage up to 1497.6 MHz (895 mV). The chip
is rated to 2150.4 MHz at 1 V, and the rest needs Linux to set the rail. Stock does it
through the L2 SAW (`msm_spm_set_vdd()`), so the route is mainline's `qcom,saw-reg`
support in `qcom_spmi-regulator` with s5 as the SAW leader; check what SAW version that
code expects against the L2 SAW here (0x20010000 at +0xfd0, SAW2 v2.1) before trusting
it. Then widen s5's constraints and add the OPPs above 1497.6 MHz. Thermal already
throttles four loaded cores at 1.5 GHz near 75 C, so sustained gains are modest;
single-thread bursts gain most.

## Camera, front (IMX132)

Same method as the rear: its stock file is `SEM02BN1_IMX132.dat`. Its CCS limits are
broken (PLL op minimum above maximum), so it needs a quirk of its own first.

## Later

- The CAMSS IOMMU, which would let CAMSS use scattered buffers (`0115` takes
  contiguous ones without it).
- Small cleanups: `THERMAL_EMULATION`, the leftover half of the CPU wedge work, the
  cosmetic 307200 kHz warning, and `/boot` mounting as an unchecked filesystem.
- Audio stays parked.

## Working rules on this phone

- Power off is Power + Volume Up. Plugged in, it switches itself back on.
- Fastboot: hold Volume Up while plugging in, flash, then `fastboot reboot`.
- Run anything risky detached (`systemd-run`) and log to persistent storage with
  `sync` after each line; `/run` and `/tmp` do not survive the reset you are
  debugging.
- Never read camss registers through `/dev/mem` while their clocks are off.
- `pstore` is empty here even after a clean reboot; do not reason from its
  emptiness.
