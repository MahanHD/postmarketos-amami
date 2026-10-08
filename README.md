# postmarketOS on the Xperia Z1 Compact

Patches, tools and notes for running mainline Linux on the Sony Xperia Z1 Compact
(D5503, codename `amami`, Snapdragon 800 / msm8974) under postmarketOS v26.06 with
kernel 6.16.12.

postmarketOS archived this device in June 2026 as unmaintained, and mainline had
no display support for it at all: the shared `qcom-msm8974-sony-xperia-rhine.dtsi`
has no display nodes, so the panel had to be written from scratch using Sony's
downstream device tree as reference. Most of what follows started that way, by
reading what Sony's kernel and firmware do and then finding the smallest change
that makes mainline do the same.

## Status

| Area | State |
| --- | --- |
| Display (720x1280 panel) | Works; the driver covers all four panel variants, tested on the JDI one |
| Touchscreen | Works |
| GPU (Adreno 330, freedreno) | Works, Xfce runs accelerated |
| WiFi, Bluetooth | Work, with factory MAC addresses |
| USB networking, SSH | Work |
| Charging, battery percentage and temperature | Work |
| Sensors | Accelerometer, gyroscope, magnetometer, proximity and light all work |
| Notification LED, vibrator | Work |
| CPU frequency scaling (300-960 MHz) and thermal throttling | Works |
| GPU frequency scaling and throttling | Works |
| CPU hotplug | Works |
| Suspend | s2idle works; deep suspend works but saves nothing here |
| Rear camera (Sony IMX200, 20.7 MP) | Works in GNOME Snapshot through libcamera: live preview, auto exposure and white balance; no autofocus yet |
| Front camera (Sony IMX132) | Identified, not started |
| Audio | No sound yet: the codec probes and its registers work, but no data moves over SLIMbus |

## Repository layout

    patches/          the kernel patch series, applied in number order
    patches/debug/    diagnostic patches, numbered from 9000 (see its README)
    recipe/           the kernel APKBUILD and config exactly as built
    recipe/libcamera/ libcamera patches and the IMX200 tuning file
    tools/            helper scripts (boot image, firmware unpacking, probes)
    tools/camera/     capture and analysis scripts for the rear camera
    userspace/        MAC address service, journald setting, camera udev rule and
                      libcamera configuration
    docs/building.md  building, flashing and the first-boot setup
    docs/notes.md     what each part needed and why, with the measurements
    docs/next-steps.md  current state and what comes next
    docs/worklog.md   the full chronological log
    docs/golden-reference/  audio register dumps from the stock firmware
    docs/measurements/      raw data behind the power numbers

## Building

The short version, with the details in `docs/building.md`:

1. `pmbootstrap init` with device `sony-amami`, channel v26.06 and the Xfce UI.
   The device is archived on edge, so v26.06 has to be chosen deliberately.
2. Copy `recipe/APKBUILD`, `recipe/config-postmarketos-qcom-msm8974.armv7` and the
   patches into the `linux-postmarketos-qcom-msm8974` aport, add the Adreno 330
   firmware from linux-firmware, run `pmbootstrap checksum` and build.
3. Install the rootfs with TWRP and `dd`, then build the boot image with
   `tools/mkbootimg.py` and write it to the boot partition.

Two things are easy to get wrong. The camera and media options must stay modules;
built in, they stop the kernel booting. And writing the boot partition only updates
built-in drivers, so after a kernel change install the package as well, or the old
modules keep loading without complaint.

## The patch series

Only the patches listed in `recipe/APKBUILD` are applied. The others stay in the
directory because they hold work that was expensive to recover, mostly device-tree
data for features that are not worth their cost yet.

**Bring-up and display**

- `0001` enables the WCNSS remoteproc (WiFi and Bluetooth) and fixes two
  touchscreen problems: the wrong I/O rail and a startup delay far too short.
- `0003` is the panel driver, generated from Sony's command blobs with
  `tools/convert_cmds.py`, and `0004` wires the display into amami's device tree.
- `0011` stops MDP5 carrying a stale hardware pipe across suspend, which made every
  suspend after the first fail.
- `0013` fixes the WLED3 brightness register stride. It had been leaving one of the
  two backlight strings dark, which looked like a hardware gradient.

**WiFi**

- `0006`, `0009` and `0010` fix wcn36xx scanning on this firmware: a message it
  does not implement, an enum padding value sent as the scan type, and an offloaded
  scan used without the capability bit that describes it.
- `0008` corrects the WCNSS interrupt type, which is what stopped the driver ever
  being reloaded.
- `0002` adds a `scan_offload` parameter. It is no longer needed and is kept as a
  debugging switch.

**Power, battery and thermal**

- `0005` and `0070` give the charger a voltage, a percentage and a temperature.
  `0069` and `0071` scale and wire the battery thermistor, and `0024` widens the
  temperature band without which the charger refuses to charge.
- `0023` fixes the current ADC, which reported zero below an amp and had the sign
  wrong on discharge. Every power measurement depends on it.
- `0012` and `0016` give the GPU and CPU thermal zones something to throttle.

**CPU**

- `0014` and `0015` add the HFPLL data and the Krait clock tree, which gives the CPU
  frequency scaling for the first time.
- `0022` gives each Krait core its own cpufreq policy. Sharing one dragged
  power-collapsed cores into every frequency change and wedged them.
- `0079`-`0081` make CPU hotplug work: the dying core collapses properly, is
  released again on the way back, and is allowed to leave the collapse loop.
- `0072`-`0076` are the L2 SAW, the MPM wakeup controller and its routing. They
  are what deep suspend needs; the suspend ops themselves (`0077`, `0082`-`0084`)
  are not in the build, because deep suspend measured no better than s2idle.

**Sensors**

- `0007` maps the sensor registry group the DSP needs before it will bring up the
  accelerometer.
- `0028`, `0045`, `0047` and `0048` fix the sensor manager: duplicate sensor IDs,
  sample rates for every data type, a second subscription that proximity needs to
  report anything, and ambient light as its own device.
- `0029` fixes an `ocmem` bit-number/bitmask mix-up.

**GPU memory**

- `0089` stops the GPU shrinker dereferencing a NULL file on objects that live in
  the VRAM carveout. That oops killed kswapd under memory pressure.
- The GPU and MDP IOMMU work (`0017`-`0019`, `0025`-`0027`, `0032`-`0038`) is kept
  but out of the build. The GPU renders through its IOMMU without faults, but it
  costs about five times the throughput and frees no memory until the display
  controller has an IOMMU too.

**Audio** (`0039`-`0044`, `0049`-`0068`)

The ADSP audio services, a SLIMbus controller for msm8974, and a WCD9320 (Taiko)
codec driver, which mainline did not have. The codec probes and all of its
registers work, but no samples move over SLIMbus in either direction yet.

**Camera** (`0085`-`0104`)

- `0085`-`0087` add msm8974 support to CAMSS. The block matches msm8916's, which
  mainline already supports.
- `0090` lists only the MCLK rates the clock controller can actually make. 24 MHz
  had been silently turning into 120 MHz.
- `0091`-`0096` fix the generic CCS sensor driver for these Sony SMIA parts:
  junk in CCS-only limit registers, sub-device state broken by the 6.16 conversion,
  the IMX200's identification and PLL model, the sensor being started twice, and
  the helper every quirk register table goes through.
- `0097` lets the board set the CSIPHY settle time; the IMX200 needs far less than
  the D-PHY formula gives.
- `0098` writes the IMX200's init and readout-window tables from the stock firmware,
  and turns off the sensor's own lens-shading correction, which starts enabled with an
  empty table.
- `0099` sizes the msm8974 CSID and VFE clocks for their 16-bit data paths; camss
  assumed wider ones, and four-lane frames came through corrupted or not at all.
- `0100` adds the rear camera to amami's device tree.
- `0101` is a driver for the rear module's focus actuator, a ROHM BU64296GWX, with the
  protocol taken from Sony's camera library, and `0102` wires it up.
- `0103` is a driver for the IMX200 itself, built from the stock firmware's tables. It
  gives libcamera a normal sensor with four modes, from 1312x988 at 96 fps to 5248x3936
  at 16.8 fps, and programs the lens shading from the module's EEPROM as stock does.
  `0104` switches the device tree to it. `0091`-`0098` (CCS) stay for reference.

The debug patches that matter right now are the camera ones: `9006` (CAMSS on
arm32), `9007` (the front sensor, not yet working) and `9010` (contiguous buffers
without an IOMMU).

Patches that touch shared msm8974 files should help the Z1 (`honami`) and Z Ultra
(`togari`) too, though neither has been tested. Several are not specific to this
phone at all, for example `0008`, `0011`, `0013` and `0089`.

## Using the stock firmware

A lot of this port comes from Sony's own software rather than guesswork:

- the panel command sequences and most device-tree data from Sony's GPL kernel and
  the stock device tree (`tools/romdtb.py` reads it without `dtc`);
- the WiFi, Bluetooth and DSP firmware from the LineageOS images;
- the camera register tables from the stock system image. `tools/unsin.py` unpacks
  Sony's SIN v3 files from the FTF, and `tools/semcdat.py` dumps the per-module
  camera files in `/system/vendor/camera/`.

None of Sony's files are in this repository.

## Camera quick start

With the kernel and `recipe/libcamera` installed (see `docs/building.md`), open GNOME
Snapshot, or list the camera with `cam -l`. For raw frames, as root on the phone:

    SIZE=2624x1976 FOCUS=330 tools/camera/capture.sh 4 1000 128

and on the host:

    SIZE=2624x1976 tools/camera/raw10.py capture.raw png photo.png

`docs/notes.md` explains the driver, the stock tables it uses and the libcamera fixes.

## Credits and licence

The panel command sequences are translated from Sony's GPL-2.0 kernel release
(`sonyxperiadev/kernel`) and keep the original copyright header. The kernel work
builds on the msm8974-mainline tree and the postmarketOS packaging. Everything here
is GPL-2.0, to match the kernel.

Not submitted upstream yet.
