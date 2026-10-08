# Next steps

Where the port stands and what comes next, in order. The history behind every item
is in `worklog.md`; the settled findings are in `notes.md`.

## Current state (2026-10-07)

The phone runs kernel 6.16.12 built from `recipe/` at pkgrel 202, with the boot
image from 202 (`uname -v` prints `#203`), and libcamera from
`recipe/libcamera` at r5. Install the package for module changes and
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

## GPU (Adreno 330): the hang, first

GTK4's GPU renderer hangs the GPU: when Snapshot handles a photo, and within seconds of
starting Megapixels. The decoded hang (see `notes.md`, "The GPU hang") is a GTK widget
draw, not the camera code, so it can hit any GTK4 app. It blocks the proper camera path
(GPU debayer, small preview, full-resolution photo). The cairo renderer forced on
Snapshot by `userspace/snapshot` is a stopgap until this is fixed.

1. Record the command stream of the hanging draw (Mesa's `FD_RD_DUMP`, decoded with
   `cffdump`) and find what the a3xx chokes on.
2. Check whether the GPU running without its IOMMU (VRAM carveout) is part of it. If it
   is, the proper fix is a working GPU IOMMU, which also lets libcamera's GPU debayer
   import buffers; the September attempt worked but cost about five times the
   throughput, which itself needs explaining.
3. Fix it at the root (Mesa or kernel), then move Megapixels and Snapshot onto the GPU.

## Camera, rear (IMX200)

1. **Megapixels** (`userspace/megapixels/sony,xperia-amami.conf`): preview at 1312x988
   and full-resolution capture work from the command line; the app waits on the GPU
   hang. It also needs a colour profile (DCP) built from stock's colour matrix.
2. **Autofocus tuning.** Continuous contrast AF works (`recipe/libcamera` `0007`). It
   rescans on large sharpness changes only; tap to focus and the AF controls for apps
   are not there yet, and a scan takes a few seconds.
3. **Full-resolution photos from apps** need the GPU path above, and enough CMA for
   the capture buffers.
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
