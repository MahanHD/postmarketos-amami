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
percentage, USB networking and SSH, the gyroscope, magnetometer and proximity
sensor, the accelerometer, the RGB notification LED, suspend and resume, and
frequency scaling on the GPU.

What doesn't: audio. The DSP boots and every sensor on it works, but there is no
codec driver for sound.

## Patches

They go on top of `linux-postmarketos-qcom-msm8974` 6.16.12 from
`msm8974-mainline/linux`.

`0001` enables the WCNSS remoteproc so WiFi and Bluetooth exist at all, and fixes
two touchscreen problems (wrong I/O rail, far too short a startup delay). `0002`
adds a `scan_offload` module parameter to wcn36xx, which `0010` has made
unnecessary and which is kept only as a debugging escape hatch. `0003` is the panel driver,
about 2000 lines, most of it generated. `0004` wires up the display in amami's
device tree and adds the battery profile. `0005` gives the charger a voltage
reading and a battery percentage. `0006` stops the driver sending a scan message
this firmware doesn't implement. `0007` adds the one registry group the sensor
service needs before it will bring up the accelerometer. `0008` corrects the
wcnss wifi interrupt type, which is what stopped wcn36xx ever being reloaded.
`0009` gives the active scan type a real value instead of an enum padding
constant. `0010` makes the offloaded scan depend on the capability bit that
actually describes it, which removes the need for `scan_offload=0`. `0011` stops
MDP5 carrying a stale hardware pipe across a suspend, which is what made the
second suspend fail and every one after it. `0012` gives the GPU a cooling map,
so the thermal zone can actually throttle it. `0013` fixes the WLED3 brightness
register stride, which had been leaving all but the last backlight string dark.

`patches/debug/` holds the diagnostic patches, numbered from 9000 so they apply
last. They are not meant for a build you use day to day, but each one answered a
question from inside the kernel that could not be answered from outside, and
`9001` is what made the accelerometer fix findable at all. That directory has its
own README.

Patches 1, 2, 7 and 8 touch shared files, so they should help the Z1 (`honami`)
and Z Ultra (`togari`) too, though I haven't tested either. `0007` through `0012` are not amami-specific at all: `0007` should fix
the accelerometer on any msm8974 with sensors on the DSP, `0008` and `0012` apply to
every msm8974 -- `0008` fixes wcn36xx module reload, `0012` the missing GPU cooling
map -- `0009` and `0010` apply to every device the wcn36xx driver supports,
`0011` to every display running on MDP5, and `0013` to every WLED3 device with
more than one backlight string.

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

One smaller thing is needed alongside it. `0006` stops the driver sending
`UPDATE_CHANNEL_LIST`, which this firmware does not implement and which the
driver was sending unconditionally despite having a capability bit for it.
Confirmed absent by
`/sys/kernel/debug/ieee80211/phy0/wcn36xx/firmware_feat_caps`, which needs
`CONFIG_WCN36XX_DEBUGFS=y`.

`hal_start_scan response failed err=5` still appears per channel during software
scans. It is harmless; the scan completes and returns every network.

**Offloaded scanning: the driver checks the wrong capability bit, and `0010`
fixes it.** Every scan used to cost a ten second timeout because the driver sent
`START_SCAN_OFFLOAD` (request 204) and the firmware never answered, so
`scan_offload=0` was required. I had this recorded as firmware that advertises a
feature it does not implement. That was wrong.

There are two capability bits, not one: `SCAN_OFFLOAD` is bit 10 and
`WLAN_SCAN_OFFLOAD` is bit 27. The driver gates the offloaded scan on bit 10
alone. This firmware advertises bit 10 and **not** bit 27:

    MCC P2P DOT11AC SLM_SESSIONIZATION DOT11AC_OPMODE SAP32STA TDLS
    P2P_GO_NOA_DECOUPLE_INIT_SCAN WLANACTIVE_OFFLOAD BEACON_OFFLOAD SCAN_OFFLOAD
    BCN_MISS_OFFLOAD STA_POWERSAVE STA_ADVANCED_PWRSAVE BCN_FILTER RTT RATECTRL
    WOW WLAN_ROAM_SCAN_OFFLOAD SPECULATIVE_PS_POLL

Twenty capabilities. The dumps in the patch series that added that debugfs file
show wcn3620 with 36 and wcn3680b with 37, and both of those list `SCAN_OFFLOAD`
*and* `WLAN_SCAN_OFFLOAD`. Bit 27 is the one that means this firmware implements
the message, and pronto never claimed it. The firmware was honest throughout; the
driver was asking for something it had correctly declined to advertise.

`0010` requires both bits. The driver then falls back to the software scan by
itself, `scan_offload` can stay at its default, and the
`/etc/modprobe.d/wcn36xx.conf` workaround is gone. Verified from a cold boot with
no module options at all: no request 204 is ever sent, no timeout, and scans
return every network.

Two things were ruled out before landing on this, both worth recording so nobody
repeats them. The message length is not the problem: trimming the trailing IE
block to send 471 and then 469 bytes instead of 593 changed nothing, all three
were ignored. And the wrong scan type in `0009` is a real bug but not this one -
with `01 00 00 00` on the wire instead of `0x7FFFFFFF` the firmware still stayed
silent. `0009` still matters for hardware that does run offloaded scans, which is
where that field actually reaches firmware that reads it.

Do not set NetworkManager's
`cloned-mac-address=permanent`: this device has no valid permanent MAC in its NV
data, so the interface then refuses to come up at all with `EADDRNOTAVAIL`. The
random locally-administered MAC isn't cosmetic, it's required.

The firmware itself was never the problem. postmarketOS already ships the correct
Sony blobs through `firmware-sony-rhine`, and I wasted time assuming otherwise.
LineageOS 18.1 carries a slightly newer build, CRM 39164 against 39150, which
loads cleanly and changes nothing.

**Bluetooth needs an address, and the phone already has one.** `btqcomsmd`
registers `hci0` and then sets `HCI_QUIRK_USE_BDADDR_PROPERTY`, which tells the
core to take the address from a `local-bd-address` device tree property. No
msm8974 board in mainline defines one, and this controller has no address of its
own, so it registers as *unconfigured*. bluetoothd ignores unconfigured
controllers, so the only thing you see is

    $ bluetoothctl show
    No default controller available

even though `hci0` is sitting right there in sysfs and in `rfkill`. `btmgmt
config` is what actually says why:

    hci0:   Unconfigured controller
            missing options: public-address

The address is on the phone, in Sony's TA partition (`mmcblk0p1`). TA is a list
of units, each one a little endian id and size followed by the magic
`c1 e9 f8 3b`, four `ff` bytes, and the data. Unit 2568 holds the Bluetooth
address and 2560 the WLAN one, both stored least significant byte first, which
is the same order `bdaddr_t` and the `local-bd-address` property use, so the six
bytes go straight in unchanged. I took the unit numbers from
`/vendor/bin/macaddrsetup` in the LineageOS image rather than guessing: they are
Thumb immediates, 2568 on the Bluetooth path and 2560 on the WLAN one.

`userspace/amami-factory-macs` reads the unit at boot and sets the address on the
kernel's management socket. Doing it in userspace rather than hardcoding an
address into the device tree keeps the port device independent, and it costs
nothing: the controller only turns up about thirty seconds in, once the WCNSS
remoteproc has booted, so there is nothing to be early for.

Three parts of that were less obvious than they look:

TA is rewritten on every boot, and the active generation sits at a different
offset each time - the unit block moved by `0x60000` between two consecutive
boots here. Walking units from the start of the partition therefore finds a
perfectly valid, much shorter list that doesn't contain the MACs at all.
Searching for the 16 byte unit header works whatever the layout, and matches
exactly once.

`btmgmt` is the obvious way to set the address, and it hangs whenever its stdin
is `/dev/null` - which is exactly what systemd hands it. From a shell it is
fine, so this only appears once the thing is in a unit file. Speaking the
management protocol directly avoids the problem and drops the dependency.

The radio comes up soft blocked, and systemd-rfkill faithfully restores that at
every boot, so the service unblocks it as well. Without that you get a correctly
configured controller that nothing can power on, reported as
`PowerState: off-blocked`.

**The WLAN address is NetworkManager's, not the driver's.** wcn36xx will take a
`local-mac-address` device tree property and call `SET_IEEE80211_PERM_ADDR` with
it, but amami's device tree has none, so the interface has no permanent address
and postmarketOS's shipped `50-random-mac.conf` fills the gap with
`wifi.cloned-mac-address=stable`. That is a per-connection address derived from
the connection UUID: stable across reboots, which is why the DHCP lease never
moved, but locally administered and unrelated to the hardware. It is a
deliberate choice, matching Android's per-network randomisation, and worth
keeping.

The factory address is in TA unit 2560, next door to the Bluetooth one. Rather
than override the default globally and make the phone trackable by a fixed MAC
on every network it joins, `amami-factory-macs wlan <connection>` pins it to one
named connection and leaves the rest randomised:

    sudo amami-factory-macs wlan "Mahan"

Worth knowing that this changes the DHCP lease, since it is a different MAC.

**The DSP boots, and it is the road to sensors rather than to audio.** The adsp
remoteproc was failing at probe with `Direct firmware load for adsp.mdt failed
with error -2`, purely because the files were not there. LineageOS 18.1 carries
them, and dropping `adsp.mdt` with `adsp.b00` to `adsp.b11` into
`/lib/firmware` is the whole fix; it boots on its own at every boot after that.

No sound comes of it, for the reasons above. What appears instead is more
interesting. The APR channels turn up,

    remoteproc2:smd-edge.apr_audio_svc
    remoteproc2:smd-edge.apr_apps2

so the audio service is live and the missing half really is only the codec. And
the sensor stack wakes up, which is the part worth chasing. amami's sensors are
not on any application processor I2C bus at all: they hang off the DSP's
Snapdragon Sensor Core, and Android reaches them over QMI, which is why the
LineageOS sensor HAL is full of `sns_smgr_*` messages. This kernel already
carries the mainline drivers for exactly that - `qcom_smgr`, with IIO front ends
for accelerometer, gyroscope, magnetometer, proximity and pressure, and
`qcom_sns_reg`, which stands in for Android's sensor daemon. With the DSP
running, both probe and get one step further:

    qcom_sns_reg: Failed to load fw from: qcom/sensors/sns.reg*
    qcom_smgr 5-6: Failed to get available sensors: -ETIMEDOUT

`sns.reg` is the sensor registry, a flat binary the driver serves back to the
DSP in groups at fixed offsets, running to about 25 KB. Android generates it at
`/data/misc/sensors/sns.reg` on first boot, so it is not shipped in any ROM. It
is not in TA either - unit 2500 is exactly 64 KiB and looked promising, but it
turns out to be a SQLite key store - and pmaports packages registries only for
sdm845-era devices. The one realistic source is an Android install on this
phone: boot it once and copy the file out, which is what I did.

**With the registry in place, three of the four sensors work.** Drop the
harvested file at `/lib/firmware/qcom/sensors/sns.reg`, restart the DSP, and:

    qcom_sns_reg: firmware loaded, error above can be ignored.
    qcom_smgr 5-6: 0x0a,0: BOSCH BMG160 Gyroscope
    qcom_smgr 5-6: 0x14,0: AKM AK8963 Magnetometer
    qcom_smgr 5-6: 0x28,0: Avago APDS-9930/QPDS-T930 Proximity & Light

They come up on their own at every boot after that, about 32 seconds in, as
`qcom-smgr-gyro`, `qcom-smgr-mag` and `qcom-smgr-prox`. These are buffered IIO
devices with `s32` channels, so there are no sysfs `_raw` files to cat; enable
the channels in `scan_elements`, set `buffer/enable`, and read `/dev/iio:deviceN`.
A stationary phone reads about 1.6 deg/s of gyro bias and a sane field vector on
the magnetometer.

`qcom,msm8974` appears in that driver's supported list marked `/* untested */`,
so this does not look to have been done on this SoC before.

**The accelerometer needed one missing entry, `0007`.** Before that, the driver
said this immediately before enumerating:

    qcom_sns_reg: got request for unmapped group id=2691

The `group_map` in `drivers/soc/qcom/qcom_sns_reg.c` carries 2690 and 2692 to
2696, 2698 and 2699. 2691 is simply absent, the DSP's request for it fails, and
the BMA2X2 never appears while the other three sensors come up fine.

The offsets in that table are observed rather than documented - the comment above
it says as much - and Android's sensor daemon turned out not to contain them, so
I found 2691 by experiment instead. A module parameter to inject one extra
mapping made each candidate a module reload rather than a rebuild:

| served for 2691          | result                                          |
| ------------------------ | ----------------------------------------------- |
| nothing (upstream today) | no accelerometer, other three sensors fine       |
| a page of zeroes         | accelerometer works, but reads about 2% low      |
| `0x1700`, same as 2690   | accelerometer works, reads 9.8 m/s^2             |
| any other page           | *nothing* enumerates, all four sensors gone      |

That last row is what makes the answer convincing. If the DSP only wanted a
successful reply, every page would behave alike; instead the wrong contents take
the whole sensor stack down, so `0x1700` is real data rather than a lucky
constant. I had concluded the contents were ignored after two zero pages behaved
identically, and only caught it by testing a dense page as a control.

Two things are worth knowing if you go poking at this. Bad registry data wedges
SMGR in a way that survives both a module reload and a remoteproc restart, so
only a reboot clears it. And remoteproc numbering is not stable across boots -
`adsp` was `remoteproc2` one boot and `remoteproc1` the next - so scripts should
find it by reading `/sys/class/remoteproc/*/name` rather than hardcoding an
index.

`sns.reg` is not in this repo and should not be: it is Sony proprietary and
carries the individual device's factory sensor calibration. Harvest your own,
as described in the build notes.

**The notification LED needs `multi_intensity`, not `brightness`.** It shows up
as `/sys/class/leds/rgb:status` with a `max_brightness` of 511, and writing that
brightness on its own does nothing at all. It is a multicolor LED whose
`multi_intensity` starts at `0 0 0`, and brightness only scales those channels,
so sysfs takes the write, reads back exactly what you set, and the LED stays
dark. I had it written off as broken on that basis.

The channel order is `blue green red`, which `multi_index` will tell you and
which is not what you would guess. Red is therefore:

    echo "0 0 255" | sudo tee /sys/class/leds/rgb:status/multi_intensity
    echo 511       | sudo tee /sys/class/leds/rgb:status/brightness

All three channels drive independently and combine to white. Turning it off
means zeroing both files. No trigger is set by default, so nothing in the
desktop drives it yet.

**A thin red frame around the screen is the X scaler, not the panel.** Xfce's
display dialog had a 0.8 scale set on `DSI-1`, so X rendered 576x1024 and the
CRTC transform stretched it to the panel's 720x1280 with a bilinear filter. At
the very edge that filter samples past the source image and leaves a one or two
pixel red fringe on all four sides.

It is easy to misread. It sits *underneath* the desktop, so the compositor paints
over it most of the time and it only flickers into view during repaints, which
makes it look touch-related. Turning compositing off makes it constant, which is
the quickest way to tell it apart from a genuine panel artefact - a panel or MDP
problem would not care what the compositor is doing. Worth checking `xrandr
--verbose` for a `Transform` other than identity before going anywhere near the
display driver. I lost time on MDP interface underruns first; there were only two
in ten minutes, nowhere near enough to explain something constant.

`--filter nearest` keeps the scale and removes the fringe, but 0.8 nearest-
neighbour looks blocky. Running native and raising `/Xft/DPI` instead keeps
everything sharp. The scale lives in xfconf at `displays -> /Default/DSI-1/Scale`
and is re-applied at every login, so setting it back to 1 there is what makes the
fix stick - `xrandr` alone lasts until you log out.

**Suspend works exactly once, and then MDP5 refuses forever.** The first
`rtcwake -m mem` goes through cleanly. Every attempt after fails in the `prepare`
step with `-EINVAL` and nothing in `/sys/power/suspend_stats/last_failed_dev`,
which makes it look like a core PM problem rather than a driver one. Only `dmesg`
names the device:

    msm_mdp fd900100.display-controller: PM: device_prepare(): msm_kms_pm_prepare returns -22

with a `WARN` from `mdp5_pipe_release` above it, reached through
`drm_atomic_helper_disable_all`.

MDP5 tracks which hardware pipe belongs to which plane in a private global atomic
state, separate from the plane state that holds the pointer. Suspend snapshots the
current state, disables everything - which releases the pipe - and resume replays
the snapshot. The snapshot predates the disable, so it still names the old pipe.
`mdp5_plane_atomic_check` sees a non-NULL `hwpipe` whose caps match and keeps it,
so `mdp5_pipe_assign` is never called and the global state never hears about the
assignment. The two disagree from then on, and the next release trips the `WARN`.

`0011` drops the stale pointer when a plane is enabled from a disabled state,
which is safe because a disabled plane never legitimately owns one. Four cycles
afterwards, including through logind, give `success=4 fail=0`.

Two cosmetic things still happen every cycle: the panel's un-initialize DCS write
times out with `-110` going down, and MDP5 logs one underrun coming back up.

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

**The uneven backlight was a one-character driver bug, and I called it hardware.**
This is the mistake I'd most like someone else to avoid.

`WLED3_SINK_REG_BRIGHT(n)` is `0x40 + n`, but `wled3_set_brightness()` writes two
bytes at that address. So consecutive strings overlap: with brightness `0x0800`,
writing string 0 at `0x40` leaves `d840=00 d841=08`, then writing string 1 at
`0x41` leaves `d841=00 d842=08`. The real layout is two bytes per string, so what
the hardware ends up with is string 0 at `0x0000` - **off** - and string 1 at
`0x0f08`, near maximum, because its high byte was never overwritten and still
holds part of the `0x0fff` power-on default. Every other WLED3 per-string register
uses a `0x10` stride, and WLED4's brightness is `0x57 + n * 0x10`; only this one
is `+ n`. `0013` makes it `0x40 + n * 2`.

One string dead and the light guide fed from the other end is what produced the
gradient, and the surviving string sitting near maximum is why the panel still
looked bright enough not to question.

The first investigation ruled out the third WLED string - `num-strings = <2>` is
correct, driving sink 2 alone gives a dark panel, nothing is wired to it - and
then concluded the gradient must therefore be the backlight hardware. That does
not follow, and it was wrong. Two things should have stopped it. Stock firmware
and LineageOS drive the same panel and the same WLED block without the gradient,
which makes it software until proven otherwise. And `0xd840`-`0xd842` reading
`00 00 08` was already in my notes, dismissed as harmless overlap; decoding it as
two bytes per string shows one string pinned at zero.

Reading the whole block is what makes it obvious - `d844 d845` still holding
`ff 0f` is the power-on default, and a default of `0x0fff` only makes sense if
brightness is two bytes per string.

You need a kernel built with `REGMAP_ALLOW_WRITE_DEBUGFS` to poke at this live.
It's deliberately not a Kconfig option; flip the `#undef` in
`drivers/base/regmap/regmap-debugfs.c` and `/sys/kernel/debug/regmap/0-01/registers`
becomes writable as `<reg> <value>`, both hex. Reading it dumps the whole SPMI
space and is slow, so match every address you want in one `awk` pass.

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
