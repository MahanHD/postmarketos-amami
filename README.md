# postmarketOS on the Xperia Z1 Compact

Notes and patches from getting mainline Linux running properly on a Sony Xperia
Z1 Compact (D5503, codename `amami`) — display, touchscreen and an Xfce desktop
on postmarketOS v26.06 with kernel 6.16.12.

postmarketOS archived this device in June 2026 as unmaintained. Mainline had no
display support for it whatsoever: the shared `qcom-msm8974-sony-xperia-rhine.dtsi`
doesn't contain a single display node, so the panel had to be written from
scratch using Sony's downstream device tree as reference.

What works now: the 720x1280 panel, the touchscreen, Xfce with GPU acceleration
through freedreno on the Adreno 330, Bluetooth, charging, USB networking and SSH.

What doesn't: audio (the `adsp.mdt` firmware isn't available), battery percentage
(no fuel gauge driver, which has knock-on effects — see below), and WiFi only
half works. The radio comes up and scans, then the WCNSS firmware crashes. One
side of the screen is also slightly dimmer than the other and I haven't worked
out why yet.

## Patches

They go on top of `linux-postmarketos-qcom-msm8974` 6.16.12 from
`msm8974-mainline/linux`.

`0001` enables the WCNSS remoteproc so WiFi and Bluetooth exist at all, and fixes
two touchscreen problems (wrong I/O rail, far too short a startup delay). `0002`
adds a `scan_offload` module parameter to wcn36xx. `0003` is the panel driver,
about 2000 lines, most of it generated. `0004` wires up the display in amami's
device tree.

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
uniform static — not a corrupted image, which is what threw me. The full set that
works:

    MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_HSE |
    MIPI_DSI_MODE_NO_EOT_PACKET | MIPI_DSI_CLOCK_NON_CONTINUOUS

No `BURST` — downstream traffic mode is `non_burst_sync_event`.

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

**UPower will switch the phone off every three minutes.** The battery driver
doesn't expose a `capacity` attribute, so UPower reads 0%, decides the battery is
critically low, and does its critical-power action, which is PowerOff. From
outside this is indistinguishable from a hang — ping keeps working, SSH dies —
and I spent a long time chasing a kernel bug that didn't exist. `journalctl -b -1`
shows a perfectly clean `systemd-poweroff`. Both of these lines are needed,
because with `AllowRisky=false` UPower quietly ignores `Ignore` and does
HybridSleep instead:

    AllowRiskyCriticalPowerAction=true
    CriticalPowerAction=Ignore

Obviously that means nothing will save you from an actually flat battery. The
real fix is a fuel gauge driver.

**Broken WiFi costs about 110 seconds of desktop startup.** NetworkManager
auto-connects at boot, the firmware crashes partway through, and the session sits
waiting behind it. `xfce4-session` came up at 169s with the radio on and 59s with
it off. Until the firmware situation improves, turn it off.

## Debugging notes

A few dead ends worth not repeating.

`msm_mdss` interrupt counts don't tell you whether video is running — vblank
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

## Flashing

The bootloader's fastboot is minimal. It won't take a ~2 GiB image (`data too
large`) and it rejects sparse images (`Unknown chunk type`), so the rootfs has to
go on by booting TWRP and dd'ing the combined image to `/dev/block/mmcblk0p25`.
Boot partition is `mmcblk0p14`, 20 MiB.

Once postmarketOS is up, much the fastest way to iterate is writing boot images
straight to the boot partition over SSH:

    cat boot.img | ssh user@172.16.42.1 'sudo dd of=/dev/mmcblk0p14 bs=1M'

`systemctl reboot bootloader` doesn't work on this device, in case you try it.

## Licence

The panel command sequences are translated from Sony's GPL-2.0 kernel release
(`sonyxperiadev/kernel`) and keep the original copyright header. Everything here
is GPL-2.0 to match the kernel.

Not submitted upstream yet.
