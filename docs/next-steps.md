# Next steps

Where the port stands and what comes next, in order. The history behind every item
is in `worklog.md`; the settled findings are in `notes.md`.

## Current state (2026-10-08)

The phone runs kernel 6.16.12 built from `recipe/` at pkgrel 204, with the boot
image from 204 (`uname -v` prints `#205`), and libcamera from
`recipe/libcamera` at r7 and Mesa from `recipe/mesa` at r4. The GPU runs behind its IOMMU since r204 (`0034`-`0036`);
the display still uses the VRAM carveout. Install the package for module changes and
rebuild the boot image with `tools/mkbootimg.py` for anything built in or in the
device tree.

Working: display, touch, GPU, WiFi, Bluetooth, charging and battery reporting, all
sensors, the notification LED, CPU and GPU frequency scaling with thermal limits,
CPU hotplug, and suspend (s2idle). The rear camera produces real frames.

Not working: audio (no sound, see `notes.md`) and the front camera (not started).

The camera loads at boot and works in GNOME Snapshot through libcamera and PipeWire. The
old bring-up blacklist (`/etc/modprobe.d/camss-bringup.conf`) is gone; `capture.sh` still
works for raw frames.

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
2. Port kgsl's power-on shader-corruption fixup for a3xx to drm/msm. The stock kernel
   binary has it; nothing is known to need it yet.
3. Offer the Mesa fix upstream once the port is clean.

## Camera, rear (IMX200)

1. **Megapixels** (`userspace/megapixels/sony,xperia-amami.conf`): the app now runs
   without hanging the GPU. Next is checking its preview and photos, with the colour
   profile from stock's matrix (`sony,xperia-amami,imx200.dcp`), on a lit scene.
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
