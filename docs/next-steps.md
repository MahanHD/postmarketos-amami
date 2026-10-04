# Next steps

Where the port stands and what comes next, in order. The history behind every item
is in `worklog.md`; the settled findings are in `notes.md`.

## Current state (2026-10-04)

The phone runs kernel 6.16.12 built from `recipe/` at pkgrel 183, with the boot
image from pkgrel 178 (`uname -v` prints `#179`). Everything after 178 touched only
modules, so the boot image did not need reflashing; install the package for module
changes and rebuild the boot image with `tools/mkbootimg.py` for anything built in.

Working: display, touch, GPU, WiFi, Bluetooth, charging and battery reporting, all
sensors, the notification LED, CPU and GPU frequency scaling with thermal limits,
CPU hotplug, and suspend (s2idle). The rear camera produces real frames.

Not working: audio (no sound, see `notes.md`) and the front camera (not started).

The camera modules are blacklisted on the phone by
`/etc/modprobe.d/camss-bringup.conf` (`qcom_camss`, `i2c_qcom_cci`, `imx219`, `ccs`),
so nothing camera-related loads at boot. `tools/camera/capture.sh` loads them with
`--ignore-install`. Remove that file once capture is reliable.

## Camera, rear (IMX200)

1. **Turn the debug patches into real ones.** The init table and mode-0 size tables
   belong in the IMX200 quirk without a module parameter (`debug/9013`); the CSID and
   VFE clock sizing for msm8974 (`debug/9012`) needs a proper rule; and camss should
   compute a settle count that catches frame starts (it computes 11, the sensor needs
   2) instead of `setsettle.py` poking it at stream start.
2. **Find where stock sets the PLL.** Not in the `.dat` tables and not in the stock
   kernel; it is in Sony's userspace camera stack (`libcammw`, `libcacao_*`,
   `libexcal_*`). Matching stock's lane rate would let the mode-0 clock and D-PHY
   registers go in too.
3. **Lens shading and colour.** Stock's per-module tuning sits in
   `vendor/camera/SOI20BS0/`. Until then every frame shows coloured blotches.
4. **Stream reliability.** A second stream after a failed one wedges camss; one
   stream per boot is the rule for now.
5. **Autofocus (BU64296G)** and the EEPROM's calibration data.

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
