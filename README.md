# postmarketOS on the Xperia Z1 Compact

Notes and patches from getting mainline Linux running properly on a Sony Xperia
Z1 Compact (D5503, codename `amami`): display, touchscreen and an Xfce desktop
on postmarketOS v26.06 with kernel 6.16.12.

postmarketOS archived this device in June 2026 as unmaintained. Mainline had no
display support for it whatsoever: the shared `qcom-msm8974-sony-xperia-rhine.dtsi`
doesn't contain a single display node, so the panel had to be written from
scratch using Sony's downstream device tree as reference.

What works now: the 720x1280 panel, the touchscreen, Xfce with GPU acceleration
through freedreno on the Adreno 330, WiFi, Bluetooth, charging, battery
percentage, USB networking and SSH.

What doesn't: audio, though the `adsp` firmware is now in hand and untried. One
side of the screen is also slightly dimmer than the other, which as far as I can
tell is the backlight itself rather than anything software can reach.

## Patches

They go on top of `linux-postmarketos-qcom-msm8974` 6.16.12 from
`msm8974-mainline/linux`.

`0001` enables the WCNSS remoteproc so WiFi and Bluetooth exist at all, and fixes
two touchscreen problems (wrong I/O rail, far too short a startup delay). `0002`
adds a `scan_offload` module parameter to wcn36xx. `0003` is the panel driver,
about 2000 lines, most of it generated. `0004` wires up the display in amami's
device tree and adds the battery profile. `0005` gives the charger a voltage
reading and a battery percentage. `0006` stops the driver sending a scan message
this firmware doesn't implement.

Patches 1 and 2 touch shared files, so they should help the Z1 (`honami`) and
Z Ultra (`togari`) too, though I haven't tested either.

## Things that took a while to work out

Most of the time here went on figuring out what the hardware wanted rather than
writing code. Recording the awkward parts in case they save someone else the
trouble.

**There are four panel variants and you have to detect which one you have.**
Sony put several panel vendors behind the same Novatek controller and picks
between them at runtime by reading DCS register `0xA1`. Byte 3 tells you which:
`0x57` is JDI, `0x00` is AUO, `0x43` is a newer AUO. The `somc,panel-id = [ff]`
entry in the vendor DT looks like a fourth panel but it's a wildcard fallback.
I implemented that one first and got a black screen for my trouble. This device
reads `40 a5 57 57`, so JDI. The driver now carries all four and picks at probe.

**The clock lane has to be non-continuous.** Sony sets
`qcom,mdss-dsi-bllp-power-mode` and `-bllp-eof-power-mode`, meaning the link
drops to low power during blanking. In mainline terms that's
`MIPI_DSI_CLOCK_NON_CONTINUOUS`. Leave it out and the clock runs continuously in
high speed, the panel never locks onto a frame boundary, and you get beautifully
uniform static, not a corrupted image, which is what threw me. The full set that
works:

    MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_HSE |
    MIPI_DSI_MODE_NO_EOT_PACKET | MIPI_DSI_CLOCK_NON_CONTINUOUS

No `BURST`; downstream traffic mode is `non_burst_sync_event`.

**`set_display_on` goes in `.enable()`, not `.prepare()`.** DRM calls `prepare()`
before the DSI host starts sending video. Switch the panel on there and this
controller latches its own uninitialised internal memory and ignores the incoming
stream from then on. Symptom is static that never changes no matter what you
write to the framebuffer.

**`prepare_prev_first = true` is needed**, otherwise every DCS transfer fails
with `-EINVAL` because the host isn't up yet when `prepare()` runs.

**Send the shutdown commands in LP mode.** In high speed the msm DSI host waits
for a completed video frame before each transfer, and during teardown that frame
never comes, so every command blocks for ten seconds (`wait for video done timed
out`). This one bug shows up wearing several different hats: killing Xorg appears
to hang the device, lightdm dies with `CreateSession: Device timeout`, and sshd
stops responding while ping still works. All of them are just waiting.

**The touchscreen needs 200ms, not 10.** Mainline has
`syna,startup-delay-ms = <10>`; Sony's DT waits 200 after reset. With 10 the
controller never answers and probe fails with `rmi_set_page: set page failed: -6`.
There's no touch reset GPIO on this board. Mainline also carries
`touchscreen-inverted-x` for this panel, which is wrong and mirrors touch
left to right.

**UPower will switch the phone off every three minutes.** Before `0005` the
battery driver exposed no `capacity` attribute, so UPower read 0%, decided the
battery was critically low, and did its critical-power action, which is PowerOff.
From outside this is indistinguishable from a hang (ping keeps working, SSH dies)
and I spent a long time chasing a kernel bug that didn't exist. `journalctl -b -1`
shows a perfectly clean `systemd-poweroff`. The stopgap was to disable the action
entirely, which needs both lines, because with `AllowRisky=false` UPower quietly
ignores `Ignore` and does HybridSleep instead:

    AllowRiskyCriticalPowerAction=true
    CriticalPowerAction=Ignore

That is no longer necessary. `0005` reads VBAT through the PMIC's ADC and turns it
into a percentage against Sony's discharge curve, so UPower now sees a real number
and the config is back to `false` / `PowerOff`.

The charger reports nothing useful on its own, so the voltage comes from the VADC
channel the PMIC already has (`VADC_VBAT_SNS`), which mainline registers as a raw
channel with no scaling. Switching it to `VADC_CHAN_VOLT` gets microvolts out,
prescale index 1 being the 1:3 divider that the scaling code already knows how to
undo. The percentage is then `power_supply_ocv2cap_simple()` against a
`simple-battery` profile built from the 25C column of Sony's
`qcom,pc-temp-ocv-lut`. It reads high while charging, since an open-circuit curve
doesn't know about the charger pushing the terminal voltage up, but it is close
enough that nothing thinks the battery is flat.

One trap here. `iio_read_channel_processed()` returns `IIO_VAL_INT`,
which is 1, on success rather than 0. Treating any non-zero return as an error
means the property never gets assigned and userspace reads uninitialised stack
memory. It presents as a wildly varying negative percentage, and because the
voltage helper fills its value in before returning, `voltage_now` looks perfectly
correct the whole time you are staring at it.

**Adding `io-channels` to the charger node killed USB.** This one fails
silently and the phone still boots, so it took a while to pin down. The USB
controller and its PHY get their VBUS state from the charger's extcon, and
fw_devlink parses `extcon` and `io-channels` alike, so pointing the charger at the
ADC quietly made USB wait on it. The charger still probes and prints nothing
unusual. It just probes late enough that `/sys/class/udc` is empty when the
initramfs looks. The gadget is only set up once, there, so USB stays dead for the
entire boot while the display and desktop come up exactly as normal.

The fix is one property, `post-init-providers = <&pm8941_vadc>`, which carries
`FWLINK_FLAG_IGNORE` and drops that dependency edge.

Diagnosing it is harder than it should be, because the initramfs's `info()` is a
no-op unless `log_info=y`, so "No UDC found, skipping gadget setup..." never
prints. What you actually see is `cat: can't open
'/sys/kernel/config/usb_gadget/g1/UDC'`. If USB is gone entirely, hold Volume Up
while plugging in for Sony's fastboot. The bootloader's USB stack is independent
of Linux, so that still works. Flash a known-good boot image and read the failed
boot with `journalctl -b -1`. Identify boots by the `#NN` build number in
`Linux version`: this device's RTC is wrong, so the timestamps lie to you.

**WiFi needs power save disabled, and nothing else.** This cost me a long time
because every symptom pointed somewhere more exotic. The firmware loads and runs;
it reports its version and capabilities happily. Authentication and association
both succeed, `RX AssocResp ... status=0 aid=1`. Then the phone immediately
deauthenticates itself, `Reason: 3=DEAUTH_LEAVING`, by local choice.

What actually happens is that `hal_enter_bmps` (the power save entry) never gets a
reply, times out after ten seconds, and wedges the firmware badly enough that
mac80211 gives up on the link. Turning power save off avoids the message
altogether:

    # /etc/NetworkManager/conf.d/98-wifi-powersave.conf
    [connection]
    wifi.powersave = 2

With that it associates, gets a lease, and holds 0% loss at about 7ms. It also
connects at boot with no delay, which is worth saying because I previously blamed
roughly 110 seconds of slow startup on having the radio enabled. That was wrong.
The delay was WiFi *failing*, not WiFi being on, and it went away once it worked.

Two smaller things are needed alongside it. The firmware advertises the
SCAN_OFFLOAD capability but never answers `START_SCAN_OFFLOAD` (request 204), so
offloaded scanning has to be turned off and the software path used instead:

    # /etc/modprobe.d/wcn36xx.conf
    options wcn36xx scan_offload=0

And `0006` stops the driver sending `UPDATE_CHANNEL_LIST`, which this firmware also
doesn't implement, and which the driver was sending unconditionally despite
having a capability bit for it. Confirmed absent by
`/sys/kernel/debug/ieee80211/phy0/wcn36xx/firmware_feat_caps`, which needs
`CONFIG_WCN36XX_DEBUGFS=y`.

`hal_start_scan response failed err=5` still appears per channel during software
scans. It is harmless; the scan completes and returns every network.

Two traps worth knowing. Any HAL operation that times out wedges the driver so
thoroughly that it cannot re-probe, failing with `-ENXIO: IRQ tx not found`, and
only a reboot brings `wlan0` back. And do not set NetworkManager's
`cloned-mac-address=permanent`: this device has no valid permanent MAC in its NV
data, so the interface then refuses to come up at all with `EADDRNOTAVAIL`. The
random locally-administered MAC isn't cosmetic, it's required.

The firmware itself was never the problem. postmarketOS already ships the correct
Sony blobs through `firmware-sony-rhine`, and I wasted time assuming otherwise.
LineageOS 18.1 carries a slightly newer build, CRM 39164 against 39150, which
loads cleanly and changes nothing.

## Debugging notes

A few dead ends worth not repeating.

`msm_mdss` interrupt counts don't tell you whether video is running. vblank
interrupts get disabled when nothing is waiting on them, so a static count proves
nothing. Use `DRM_IOCTL_WAIT_VBLANK` (`0xC00C643A` on arm32).

Writes to `/dev/fb0` go nowhere on this platform. There's no IOMMU, so the
display runs from a physically contiguous VRAM carveout and the generic fbdev
path can't reach it (`fb0: Framebuffer is not in virtual address space`). Use X.

Writing to the carveout through `/dev/mem` proves nothing either, since the
mapping is cached and the writes may never reach the memory the display
controller actually reads.

And the big one: if SSH dies while ping still works, check `journalctl -b -1` for
an orderly poweroff before assuming the kernel hung.

The uneven backlight is not the third WLED string, which was my first guess.
`rhine.dtsi` sets `qcom,num-strings = <2>`, so the driver drives sinks 0 and 1 and
leaves sink 2 alone, and it looked plausible that amami has a string the shared
file doesn't know about. It doesn't. Driving sink 2 on its own (`CURR_SINK` at
`0xd84f`, bits 7:5) gives a completely dark panel, so nothing is wired to it and
the device tree is right. Raising `num-strings` to 3 changes nothing either.

Worth knowing if you go poking at this: `WLED3_SINK_REG_BRIGHT(n)` is `0x40 + n`
but the driver writes two bytes per string, so consecutive strings overlap and
overwrite each other. After a normal update `0xd840`-`0xd842` read `00 00 08`
rather than anything per-string. Brightness on WLED3 is effectively global.

You need a kernel built with `REGMAP_ALLOW_WRITE_DEBUGFS` to try any of this. It's
deliberately not a Kconfig option; flip the `#undef` in
`drivers/base/regmap/regmap-debugfs.c` and `/sys/kernel/debug/regmap/0-01/registers`
becomes writable as `<reg> <value>`, both hex.

## Flashing

The bootloader's fastboot is minimal. It won't take a ~2 GiB image (`data too
large`) and it rejects sparse images (`Unknown chunk type`), so the rootfs has to
go on by booting TWRP and dd'ing the combined image to `/dev/block/mmcblk0p25`.
Boot partition is `mmcblk0p14`, 20 MiB.

Once postmarketOS is up, much the fastest way to iterate is writing boot images
straight to the boot partition over SSH:

    cat boot.img | ssh user@172.16.42.1 'sudo dd of=/dev/mmcblk0p14 bs=1M'

That is only half an update, though. Not everything is built in: `QCOM_SPMI_VADC`
and `QCOM_VADC_COMMON` are modules, and modules live on the rootfs, so writing the
boot partition alone leaves the old ones in place. Worse, vermagic only encodes
the version and SMP/PREEMPT, not the build number, so stale modules load without a
word of complaint. A patch touching both a built-in and a module then looks half
applied, which is a genuinely confusing thing to debug. Install the package as
well:

    scp linux-...apk user@172.16.42.1:/tmp/
    ssh user@172.16.42.1 'sudo apk add --allow-untrusted /tmp/linux-...apk'

`systemctl reboot bootloader` doesn't work on this device, in case you try it.

## Licence

The panel command sequences are translated from Sony's GPL-2.0 kernel release
(`sonyxperiadev/kernel`) and keep the original copyright header. Everything here
is GPL-2.0 to match the kernel.

Not submitted upstream yet.
