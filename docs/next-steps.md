# Next steps

Where the port stands and what comes next, in order. The history behind every item
is in `worklog.md`; the settled findings are in `notes.md`.

## Current state (2026-10-12)

The phone runs kernel 6.16.12 built from `recipe/` at pkgrel 206, with the boot image
from 206 (`uname -v` prints `#207`). `0105` (kgsl's power-on fixup) was tried twice, as
r205 and r207, and reverted both times (GPU item 2). There is no phone backup (`backups/README.md`). Userspace
from this repo: libcamera r7 (`recipe/libcamera`), Mesa r4 (`recipe/mesa`), libmegapixels
r1 and Megapixels r2 (`recipe/libmegapixels`, `recipe/megapixels`), with
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

**Where to pick up:** the GPU list below. r206 hangs about three times an hour under
`tools/gpu-soak.sh` (item 4); the kgsl power-on fixup made that worse (item 2). Tests that
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
   the stock kernel's (`tools/re/kgsl-fixup-emu.py`), the microcode is identical, and it
   now runs the way kgsl runs it, and it is confirmed to execute. Still, it makes things
   worse: 10 hangs and 17 hw_init idle timeouts in an hour, against 3 and none without
   it. Before trying again: do the negative control for the `HLSQ_CL_*` readback on r206;
   try ending the fixup with a330v2's `RBBM_CLOCK_CTL` bits (10, not the hardcoded 00);
   and look at what kgsl's start sequence sets that drm does not.
3. Carveout buffers are cleared on allocation since r206 (`0106`); that removed the
   "Division by zero" warnings and the cross-process data leak.
4. The GPU still hangs on the fixed Mesa: 3 times in an hour of `tools/gpu-soak.sh` on
   r206 (one Xorg, two Megapixels), all recovered. All three saved Xorg dumps hung in
   the first one to three jobs after a power-on (rptr 36, 50, 54), yet 5943 power-ons
   under `tools/gpu-pwron-stress.py` gave no hang, so a power-on is not enough by
   itself. `xorg-hang.devcore`: pipeline idle, both IBs read, the CP busy with a
   non-real-time memory operation. Next: catch a devcoredump of each new hang (they
   expire after five minutes) and look for what they share.
5. GPU recovery can fail for good: after one hang at 21:39 (Xorg, still on the old Mesa)
   every reset left the GPU unable to finish anything until a reboot. Earlier the same day
   it recovered from dozens of hangs. Decode `work/mesa/stuck.devcore` and find out why.
6. Offer the Mesa fix upstream once the port is clean.

## Camera, rear (IMX200)

1. **Megapixels** (`userspace/megapixels/sony,xperia-amami.conf`, `recipe/megapixels`):
   it previews live on the GPU, white is white, and auto exposure now has the whole 30 fps
   frame (`recipe/libmegapixels`). Clipped highlights turn pink: clip after white
   balance in its shader, as libcamera's `0005` does.
2. **Autofocus tuning.** Continuous contrast AF works (`recipe/libcamera` `0007`). It
   rescans on large sharpness changes only; tap to focus and the AF controls for apps
   are not there yet, and a scan takes a few seconds.
3. **Full-resolution photos from apps** need a GPU debayer (Megapixels does its own; the
   libcamera one still needs an msm IOMMU for the display), and enough CMA for the
   capture buffers.
4. **Tuning.** White balance and exposure are libcamera's simple defaults. The EEPROM's
   remaining bytes and stock's `exposure_ctrl.dat` may hold better starting points.
5. **The first binned frames** come out at full size, because stream-on resets the mode.
   This also wedges camss when Megapixels starts the 2624x1976 mode, so that mode is left
   out of its config until the sensor's mode switching is understood (stock's 0x3004
   group is the lead).
6. **Stream reliability.** A stream after a failed one can still wedge camss.

## CPU above 960 MHz

The chip is rated to 2.15 GHz (speed2-pvs4, table in `notes.md`), but more than 960 MHz
needs Linux to drive VDD_APC, which stock does with its `krait-regulator` driver and
PM8841. That driver has to be ported from Sony's kernel; raising the clock without it
would under-volt the CPU.

## Camera, front (IMX132)

Same method as the rear: its stock file is `SEM02BN1_IMX132.dat`. Its CCS limits are
broken (PLL op minimum above maximum), so it needs a quirk of its own first.

## Later

- The CAMSS IOMMU, to replace the contiguous-buffer workaround (`debug/9009`,
  `debug/9010`).
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
