# Notes

The long version: what each piece of hardware needed, the dead ends, and the
measurements behind the claims in the main README. Sections are roughly in the order
the work happened. The chronological working log, with every experiment and its
numbers, is in `worklog.md`.

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

**The panel's shutdown DCS write always timed out.** Going down, every cycle
logged `wait for video done timed out`, then `cmd dma tx failed, type=0x5,
data0=0x10, ret=-110`, then `Failed to un-initialize panel: -110`. `0x10` is
`ENTER_SLEEP_MODE`, sent from the panel's `unprepare()`.

It could never have worked there. `disable_outputs()` runs the bridge chain's
`disable` (panel `disable()`), then the encoder's, then the chain's `post_disable`
(panel `unprepare()`) - and the encoder's is `mdp5_vid_encoder_disable`, which
clears `INTF_TIMING_ENGINE_EN`. By `unprepare()` the video stream is stopped, but
the DSI host is still `enabled`/`power_on` and `STATUS0` still reads
`VIDEO_MODE_ENGINE_BUSY`, so `dsi_wait4video_eng_busy()` waits 70ms for a
video-done that will never arrive, and the command DMA - which a video-mode link
only transmits during blanking - then times out after another 200ms.

`0003` now sends both `SET_DISPLAY_OFF` and `ENTER_SLEEP_MODE` from `disable()`,
while the timing engine is still running. Downstream does the same: Sony's
`qcom,mdss-dsi-off-command` is `28` and `10` in one batch, issued before the
controller is stopped.

The timeout was also hiding a second bug. `mipi_dsi_msleep()` is a no-op once
`accum_err` is set, so the failed sleep-in skipped the 150ms settling delay that
follows it and the panel was reset immediately - the delay the code existed to
honour was the one thing it did not do. Measured over `device_pm_callback`
tracepoints, `msm_mdp fd900100.display-controller [suspend]` goes from 373.7ms to
272.9ms, and four cycles log no DSI errors at all.

**The resume underrun is not a suspend bug.** MDP5 logs one
`mdp5_irq_error_handler: errors: 04000000` (`INTF1_UNDER_RUN`) per cycle, but a
plain `xset dpms force off; xset dpms force on` produces exactly one too - three
DPMS cycles, three underruns. It fires 690ms into the resume callback, at the
encoder enable rather than when the clocks come back, so it is a real first-frame
underflow and not a stale status bit. The bandwidth vote is in place and unchanged
across suspend (`mas_mdp_port0` peak 6400 MB/s, from `fd900100.display-controller`)
and the clocks are at maximum (mdp 320MHz, AXI 400MHz). What is left is the order
in `mdp5_vid_encoder_enable`: `INTF_TIMING_ENGINE_EN` is written before
`mdp5_ctl_commit()` flushes the pipe and mixer, so the interface asks for pixels
just before the configuration lands. That is generic MDP5 code shared by every
SoC that uses it, it costs one frame while the panel has not latched video yet,
and it is left alone deliberately.

**The CPU had no frequency scaling, and mainline had all the drivers for it.**
`qcom-cpufreq-nvmem` already lists `qcom,msm8974` with `match_data_krait`, `krait-cc`
already handles this SoC, and `qcom,msm8974-hfpll` is already in the HFPLL binding -
complete with an example using amami's own `0xf908a000`. What was missing was the
device tree to connect them, plus the one `hfpll_data` entry the binding implies.
No arm32 DT in the tree wires Krait cpufreq: not msm8974, not apq8064, not ipq8064,
not msm8960. The upstream series that would have added it ran from 2014 to 2018 and
was reworked in 2023; the drivers and bindings landed, the DT never did.

`qcom,krait-cc-v2` turns out to be exactly the msm8974 case. The v1/v2 split is not
"msm8960 or apq8064", it is whether each CPU owns an aux clock: for v2 the driver
registers `qsb` and `acpu_aux` itself as `gpll0_vote / 2`, so no `kpss-gcc` or
`kpss-xcc` wiring is needed - which matters, because `kpss-xcc` only ever matches
`qcom,kpss-acc-v1` and this SoC is `-v2`.

The HFPLL entry in `0014` differs from the `qcs404` one already in the file by a
single field: `config_val`, `0x430405d` to `0x4d0405d`. Offsets, `user_val`, VCO mask
and rate limits are all identical.

The numbers came out of the ROM. Downstream msm8974 does not use the `acpuclock-*`
family, it uses `clock-krait-8974`, and that binding keeps its data in the device
tree - so LineageOS's own `boot.img`, unpacked through its `QCDT` container, carries
`/soc/qcom,clock-krait@f9016000` with the HFPLL addresses, the config value, and a
per-bin frequency-to-voltage table.

Which bin applies is in the fuses. `get_krait_bin_format_b` reads eight bytes and
carries its own validity bits, and `0xb0` in `qfprom0` is the only offset where both
are set: **speed bin 2, PVS bin 4, version 0**, later confirmed verbatim by the
kernel itself once the driver was live. Downstream's `reg` for `efuse` is
`0xfc4b80b0`, the raw region behind the ECC-corrected shadow mainline maps, which
agrees. For this bin the ladder tops out at **2150.4MHz**, not the 2265600 top row of
`qcom,cpufreq-table` - that table is bin-independent, the PVS table is what governs,
and 2.15GHz is exactly the MSM8974AA rating.

**The table stops at 960MHz on purpose.** Nothing in mainline can drive VDD_APC.
Downstream runs `qcom,krait-pdn` with per-core `qcom,krait-regulator` LDOs and
`qcom,krait-regulator-pmic`, none of which exist here, and mainline's only
alternative - the `qcom,saw-reg` path in `qcom_spmi-regulator.c` - has no DT users on
any platform. The rail also cannot be read: PM8841 returns zeroes over SPMI even for
its type and subtype registers, so unlike PM8941 it is simply not reachable. What can
be established is where the bootloader leaves the cores, because `krait-cc` prints it
at probe: `CPU0 @ 960000 KHz`, all four. Downstream wants 820000uV there, the phone
has already booted at that rate, so every OPP at or below it is covered by whatever
the rail is doing anyway. Raising the ceiling further is an under-volted overclock
until the rail is controllable.

That probe line also corrected a measurement. The CPU had been recorded at 799.9MHz
from `perf stat -e cycles`; it was 960MHz all along, and the discrepancy was the
busy loop forking `date` every iteration and letting the core idle. With a spinner
that does not fork, perf reads 307, 576 and 961MHz against 300, 576 and 960 asked
for. Under four-core load at 960MHz the CPUs settle at 62-63C, well under the 75C
passive trip.

**The passive trip was bound to nothing.** All four `cpuN-thermal` zones already
carried a 75C `passive` trip and a 110C `critical` one, but with no `cooling-maps`
the passive trip did nothing at all and the only response to heat was the emergency
poweroff. `0016` adds the maps, and `CONFIG_CPU_THERMAL` had to be turned on with
them.

The shape of that patch follows from who registers the cooling device. It is not
`cpufreq-dt`: the cpufreq core does it, in `cpufreq_online()`, for any driver
carrying `CPUFREQ_IS_COOLING_DEV`, and it resolves the node with
`of_get_cpu_node(policy->cpu)`. `0015` made the OPP table `opp-shared`, so the four
Kraits are one policy whose leader is CPU0, and exactly one cooling device exists.
So `#cooling-cells` belongs on `cpu0` alone - putting it on the other three would
advertise cooling devices that never get registered - and all four zones map their
passive trip to `&cpu0`. That is the right answer anyway: `thermal_cdev_update()`
takes the highest state any zone asks for, so the hottest core throttles the
cluster, which is what you want when one policy sets all four clocks together.

Verifying it needed `CONFIG_THERMAL_EMULATION`, because the trip is unreachable:
four-core load at the 960MHz ceiling tops out at 56-57C, nearly 20C short. Driven
through `emul_temp` the zone walks the whole ladder, 76C through 90C mapping onto
states 1 to 8 and 883.2MHz down to 300MHz, and releases back to 960MHz below the
trip's 2C hysteresis. Any of the four zones drives it, not just CPU0's. The cost is
that `emul_temp` also lets root feed the thermal core a fake *low* reading and mask
the 110C trip, so it is a knob worth removing once the ceiling is raised far enough
to reach 75C honestly.

**Power collapse and frequency switching cannot both be on.** With `cpu_spc` and
cpufreq both live, cores wedge: `rcu_preempt detected stalls` names two CPUs, and
`Sending NMI from CPU 2 to CPUs 0:` is followed by no backtrace at all. A core
spinning on a lock still answers an NMI; one that does not has stopped. The
surviving cores keep logging for tens of minutes, which makes it look like a boot
hang from outside - the USB gadget stays enumerated the whole time, so the host sees
a device that never answers.

It is not a boot hang, and the log says so if you do the arithmetic. Jiffies advance
7311 over 73.09s of printk timestamps, so HZ is 100; with `t=89834 jiffies` at
timestamp 927.34 the grace period began at **29.0s of uptime**. The kernel had been
alive for 26 minutes.

Five controlled runs found the pair, one variable at a time:

| cpuidle | frequency | load | result |
|---|---|---|---|
| off | free | idle | 567s clean |
| SPC on | pinned 960MHz | idle | 971s clean, 35089 collapses |
| SPC on | pinned 300MHz | idle | 669s clean |
| SPC on | **moving** | burst | **died at ~780s**, 2832 transitions |
| SPC on | pinned 960MHz | burst | 1224s clean, 0 transitions |

The last row is the one that matters: same load, same collapses, frequency held
still, survives. So it is the switching, not the load, and that makes it a
consequence of `0015`. The likely mechanism is that `0015` marks the OPP table
`opp-shared`, so all four Kraits are one policy and a governor running on any CPU
reprograms every CPU's mux and HFPLL - including cores that are power-collapsed at
that instant. Downstream does per-core DVFS coordinated with the SPM; there is no
equivalent here.

**`0015` should never have said `opp-shared` in the first place.** That property
asserts the CPUs share a clock domain and must change together. Each Krait has its
own mux and its own HFPLL, so it is simply false here - and it is what dragged
collapsed cores into every transition. `0022` drops it, which gives four independent
policies, and adds the `#cooling-cells` and per-zone cooling maps that `0016` now
needs on all four CPUs rather than only CPU0.

The first attempt at this shipped as `0021`, which disabled `cpu_spc` outright. That
worked - 5478 transitions under burst load over 22 minutes - but paid for stability
with all of the idle power saving. `0022` replaces it and keeps both: 19460
transitions and 133447 collapses over 27 minutes of burst load, 109031 collapses
over 17 minutes idle, four clean boots, no stalls anywhere.

One caveat for later: VDD_APC *is* shared between the cores even though the clocks
are not, so if the rail ever becomes controllable it will have to be driven at the
maximum any core needs. Nothing controls it today, so the point is moot.

The standard command line now carries `sysctl.kernel.panic_on_rcu_stall=1 panic=10
rcupdate.rcu_exp_cpu_stall_timeout=21000`, so if a core ever wedges again the phone
panics, saves a pstore record and reboots itself rather than needing the battery
pulled. **That third parameter is not optional**: `rcu_exp_cpu_stall_timeout` is in
milliseconds and defaults to 20, while its sibling `rcu_cpu_stall_timeout` is in
seconds, so without it the kernel panics on the harmless ~3-jiffy expedited stall
this device emits at about 36s of every boot.

## What the phone actually draws

There was no power measurement at all until `0023`, because the PM8941 current ADC
reported a flat zero. Two bugs in `qcom-spmi-iadc.c`, both upstream:

- `vsense_raw` is declared `u16`, and discharge reads *below* the calibration
  offset. Every negative current underflowed into a huge positive one - the internal
  channel was reporting a fictitious 363mV.
- `vsense_uv / rsense` divides micro volts by micro Ohms, which yields **amperes**,
  while the variable is named `isense_ua`, the debug print says uA, and
  `IIO_CHAN_INFO_SCALE` is 0.001. Integer division then truncated anything below 1A
  to zero, which is every current this phone ever draws.

Fixing both gives a working ammeter, and the two independent sense resistors -
internal and the 10 mOhm external one named in the device tree - agree within 5-7%,
which is the reason to believe the numbers:

| state | current | runtime on a 3140 mAh pack |
|---|---|---|
| idle, screen off | 252 mA | 12.5 h |
| idle, screen on | 400 mA | 7.8 h |
| four cores loaded, screen on | 689 mA | 4.6 h |

The panel and its backlight cost **148 mA**, 37% of idle draw. Resolution is about
0.55 mA per ADC count.

Two caveats. These are *awake* figures; nothing here is a suspend number, and s2idle
standby will be much lower. And `capacity` is derived from voltage through Sony's OCV
table rather than counted, so it sags under load and recovers afterwards - it read
91% idle, 83% under load, then 88% back at idle within a few minutes. Treat the
percentage as an open-circuit estimate, not a fuel gauge.

**Charging needs a real supply, not a PC port.** The phone draws about 400 mA just
to run, so a 500 mA host port leaves nothing for the pack: net battery current sits
at exactly zero, `status` reads Discharging and `capacity` barely moves, which looks
convincingly like a broken charger. On a wall charger the same kernel reports
`Charging`/`Fast` and pushes ~268 mA in at 92%, tapering towards the 4.35 V VMAX.

That is only half the story though - `0024` had to come first. `qcom_smbb` always
enables the SMBB's temperature comparators and picks their window from a single
device tree bool, and the default narrow [35%:70%] band read amami's perfectly
ordinary 642 mV `BAT_THERM` as too hot. That comparator gates the charger in
hardware, not just in reporting, so `health = Overheat` was a genuine block rather
than a cosmetic complaint. With `qcom,jeita-extended-temp-range` the band widens to
[25%:80%], `BAT_IF` real-time status reads 0x03 and health reports Good. Both changes
were needed; since they landed together the attribution is not cleanly proven, but
the mechanism says the fix was necessary and the supply was the other half.

The 642 mV figure is worth trusting because the VADC was calibrated against its own
`REF_625MV`, `REF_1250MV` and `GND_REF` channels - 97.41 uV per count - and the same
calibration reproduces `voltage_now` from `VBAT_SNS` exactly.

These were measured while polling the phone over ssh every 25s, which sounds like it
should inflate them and does not: repeating the run with nobody connected at all - an
on-device script logging to tmpfs - gives ~396 mA against 400 mA, so the entire cost
of watching is about 4 mA. The ssh traffic is visible elsewhere though. Each login
writes sshd/sudo/pam lines to the journal, and that showed up as ~13 mmc0
interrupts/s and ~70 block writes per 10s at idle with *no* process reporting
`write_bytes`, because journald mmaps its files and that accounting never sees them.
The journal had reached 617MB; `userspace/98-journal-size.conf` caps it at 64MB.

One trap when measuring standby: a touch wakes DPMS. An unattended run came back with
screen-off and screen-on within 2 mA of each other, purely because handling the phone
to unplug the cable turned the display back on. Check that `bl_power` reads 4 in the
samples rather than trusting that the blank stuck.

Measuring draw needs the USB cable **out**. On USB the battery floats: the external
sense resistor sees only noise, current does not respond to load at all, and
`capacity` barely moves. Use WiFi for the session instead.

## The proximity sensor reports nothing

*Solved since: `0047` keeps a second subscription open, after which proximity reports
normally, and ambient light became its own device with `0048`. The section below is the
investigation as it stood before that.*

It enumerates correctly - right vendor, right part, two data types - and registers an
IIO device, which is exactly why it passed for working. Its buffer yields **zero
bytes** over 25 seconds with a hand waved across it, while the accelerometer under
the same procedure yields tens of kilobytes in five. Enabling the buffer produces no
error and no dmesg output, and the buffering request to the DSP succeeds.

Two explanations have been tried and neither is it. The first was that the driver
only ever subscribes `SNS_SMGR_DATA_TYPE_PRIMARY`, so a sensor's secondary data type
is never requested - true, and it is why an ambient light channel alone can never
work, but subscribing to both types (patch `0031`, kept in `patches/` and out of the
build) leaves 0x28 just as silent. The second was the sensor registry: nine groups
are requested and unmapped (2001, 2500, 2610, 2650, 2680, 2970, 2971, 2980, 2990),
and `0007` proved a single missing group can disable a sensor outright. But that
cost the accelerometer its *enumeration*, whereas proximity enumerates fine and only
fails to report, so the registry is a poor fit. Offsets `0x2900`-`0x2cff` are unused
in `group_map[]` - four `0x100` pages against exactly four unmapped `29xx` groups -
which is suggestive, and is also exactly the guess-and-flash pattern that should be
resisted without a real source.

Upstream lists proximity as supported, so this may well be specific to this device's
APDS-9930 configuration rather than the driver.

## Why idle costs 252 mA, and why suspend is shallow

*Measured since: `0072`-`0081` made a real deep suspend work, and it saves nothing,
because cpuidle already power-collapses the cores (`cpu-spc`) and L2-off never wakes.
The build stays on s2idle. Details in `worklog.md`, "Phase 2: deep suspend".*

These are the same fact twice. `/sys/power/mem_sleep` offers only `[s2idle]`, so
`mem` quietly falls back to freeze, and that is not something waiting to be switched
on: for `deep` to exist something has to call `suspend_set_ops()` with
`PM_SUSPEND_MEM`, and **nothing in mainline does for Qualcomm ARM32**. There is no
`suspend_set_ops` anywhere under `drivers/soc/qcom`, `drivers/firmware` or
`arch/arm/mach-qcom`, and that last directory contains only `Kconfig`, `Makefile` and
`platsmp.c`. `CONFIG_ARM_PSCI` is off as well, so there is no firmware route either.

So the cores power-collapse individually - `cpu_spc` logged 35000 entries in a
20-minute soak - while the SoC around them never does. The RPM stays up, the rails
stay where they are, DDR stays refreshed and the clocks keep running. 252 mA with the
screen off is that, not a runaway. Worth stating because it looked like a bug: the
wakeup sources are clean, nothing holds a wakelock (`fe200000.remoteproc` accounts
for 575 ms in total and is not active), and at idle the only notable interrupt
sources are the arch timer, the eMMC and WiFi receive.

Closing the gap means writing platform suspend ops, driving the SPM for system-wide
power collapse rather than the per-core standalone kind, and coordinating with the
RPM to drop rails. That is a project on the scale of the GPU IOMMU. It is the single
biggest lever on battery life that remains.

## The GPU IOMMU

`msm.vram=192m` costs 192MB on a 2GB phone, and an IOMMU would give it back.
`0017` makes `qcom,iommu-secure-id` optional - downstream's `kgsl_iommu` has no
secure id, so TrustZone does not own the GPU IOMMU and the stock driver's
`-ENODEV` makes it unprobeable. `0018` adds the `gpu_iommu@fdb10000` node with its
three context banks. `0019` adds the `alt` clock, because the first attempt hung the
phone at boot with only the OXILICX interface and bus clocks.

As of the second attempt the IOMMU itself works. With the `alt` clock in place it
probes, `/sys/class/iommu/fdb10000.iommu` appears and all three context banks bind -
the first attempt hung the phone precisely because that clock was missing, the GPU
SMMU's registers needing GFX3D running and not just the OXILICX interface and bus
clocks that msm8916 gets away with.

`0025` then points the GPU at it, and that works too: the GPU joins iommu group 0,
gains an `iommu` symlink, and gets a real address space. The proof of the last part
is indirect but solid - `No memory protection without IOMMU` only prints when
`gpu->aspace` is NULL, stage one prints it and stage two does not.

The `-16` that used to stop it there is understood and fixed. It was `-EBUSY` from
`__iommu_attach_group`, and the reason is 32-bit specific: `arch_setup_dma_ops()`
calls `arm_setup_iommu_dma_ops()`, which creates its own mapping and attaches a
domain to the GPU's IOMMU group before drm/msm ever runs. The group is then no longer
on its default domain, so msm's attach is refused. Booting with `no_hash_pointers`
shows it plainly - the domain the second attach trips over is the same pointer the
DMA layer attached 100ms earlier:

    4.730  attach_group: dom=c42dbe9c cur=c17096a4 def=c17096a4
    4.838  attach_group: dom=c42e639c cur=c42dbe9c def=c17096a4
    4.843  attach_group: busy

`0026` hands the device back with `arm_iommu_detach_device()` before claiming it.
`QCOM_IOMMU` *selects* `ARM_DMA_USE_IOMMU`, so turning the IOMMU on is what enables
the glue in the first place, and no DRM driver in the tree calls that detach because
drm/msm is arm64-focused. With it, the attach returns 0 and `adreno_gpu_init`
succeeds.

**It is still not usable, one layer further down.** Once the IOMMU actually
translates, `a3xx_hw_init` reports `timeout waiting for GPU to idle!` and
`adreno_load_gpu` fails with `-22`, so mesa falls back from `FD330` to `llvmpipe`.
Every software step passes first - attach, address space, OCMEM, interconnects,
firmware, and now the BFB settings too.

Three explanations have been tried and none of them is it. OCMEM contention was
ruled out by instrumentation, which shows it allocating cleanly with `active=0x0`.
The idea that mainline's `0xffffffff` write to `SMMU_INTR_SEL_NS` is really setting
a halt bit - the prior art uses the same 0x2000 offset as `MICRO_MMU_CTRL`, bit 2
halt-request - was ruled out by skipping the write, which changed nothing; so those
offsets should be treated as unverified. And `0027` applies downstream's non-secure
BFB table from `qcom,iommu-bfb-regs`/`-data`, reporting `applied 12 bfb settings`,
with the GPU failing identically.

**The cause, found by reading downstream rather than guessing: nothing maps the GPU's
stream IDs to a context bank.** `msm_iommu-v1.c` programs the stream match table per
context from `qcom,iommu-ctx-sids` - `SET_SMR_VALID`, `SET_SMR_MASK`, `SET_SMR_ID`,
then `SET_S2CR_CBNDX` to aim that slot at the context bank and `SET_S2CR_NSCFG(3)` to
force non-secure. Mainline's `qcom_iommu.c` has none of that: on msm8916 TrustZone
does it inside `qcom_scm_restore_sec_cfg()`, and this IOMMU has no secure id, so the
call is skipped. The GPU's transactions therefore match no stream and reach no
context bank, which accounts for the hang *and* for the complete absence of fault
reports - no context bank owns the transaction, so nothing is there to report one.

Which raises a better question than "how do we teach `qcom_iommu` stream mapping",
because the register layout is a byte-for-byte match with the generic ARM SMMU
driver: the stream match table at GR0+0x800, CBAR at GR1, context banks at
base+0x8000. This hardware simply *is* an ARM SMMU, and `arm-smmu.c` already does
everything `qcom_iommu.c` cannot.

`0034` tries exactly that, and the driver agrees:

    arm-smmu fdb10000.iommu: SMMUv1 with:
            stage 1 translation / stage 2 / nested
            stream matching with 4 register groups
    arm-smmu fdb10000.iommu: SMMU address space size (0x8000) differs from
                             mapped region size (0x10000)!

That warning is the next thing in the way, and it is specific. `arm-smmu` takes
`numpage` from `IDR1.NUMPAGENDXB` and addresses context bank *n* at
`base + ((numpage + n) << pgshift)`. The ID register reports numpage 4, putting the
banks at base+0x4000, while downstream places them at `0xfdb18000` - base+0x8000 -
so the real value is 8 and the ID register under-reports. The driver is programming
the wrong addresses, which is why the GPU still fails the same way.

`arm-smmu-qcom.c` has a `cfg_probe` implementation hook for exactly this kind of
deviation - it already corrects lying ID registers on msm8998 and sdm630 - so `0035`
adds `qcom,msm8974-smmu-v1` beside them. The correction is measured rather than
assumed: writing a magic word to `CB_TTBR0` at both candidate offsets and reading it
back gives

    context bank probe at +0x4000: read back 0x00000000
    context bank probe at +0x8000: read back 0xdeadbee0

so the banks really are at base+0x8000 and `numpage` really is 8.

**With that, the GPU initialises through the IOMMU.** `a3xx_hw_init` passes, the `-22`
is gone, the device gains an `iommu` symlink pointing at `smmu.0xfdb10000`, mesa loads
`FD330`, and `msm_gpu_init` stops printing its fallback line - which only appears when
`gpu->aspace` is NULL, so a real address space is being built and used. That is the
furthest this has ever got.

What remained was a hangcheck lockup on real submissions, and the measurements were
strange enough to be worth keeping. During a hang `rptr` equalled `wptr`, so the
command processor walked the whole ringbuffer and caught up; `rbbm-status` read
`0x00000001`, idle; `gpu-irq` recorded **zero** interrupts after ten seconds of
glxgears; and the SMMU's global-fault and context-fault lines recorded zero as well,
while `last-fence` climbed and `retired-fence` trailed behind it. The control settles
that the interrupt really is the completion path: the same counter on the working
carveout kernel goes from 62 to 21,334 in twelve seconds.

So the processor consumed the ring without executing anything - no fence write, no
interrupt, no fault.

**Both halves of that turned out to be bugs, and the "no fault" half was hiding the
other one.**

The way in was to stop rebuilding and read the hardware on a running system.
`CONFIG_STRICT_DEVMEM` is off, so `/dev/mem` reaches the SMMU directly - but only
while it is clocked, and it is runtime-suspended between operations, so pin it first
or the read hangs the bus:

    echo on > /sys/bus/platform/devices/fdb10000.iommu/power/control

With that, everything checked out. `SMR(0..2)` held `0x8000000{0,1,2}` - valid, stream
IDs 0, 1 and 2 - and `S2CR(0..2)` read `0x000ca001`: type TRANS, aimed at context bank
1, with the forced `NSCFG` and `MEMATTR`. The unused fourth slot read FAULT, and
`sCR0` had `CLIENTPD` clear and `USFCFG` set, so the SMMU was enabled and unmatched
streams would fault. Walking cb1's page tables in DRAM by hand resolved the
ringbuffer's `iova 0x1001000` to `PA 0x70101000`, inside the `70100000->7c100000`
carveout the display driver prints, readable and writable. `TCR` reading zero is
correct rather than a failed write - `io-pgtable-arm-v7s` sets `tcr = 0` deliberately.

That leaves "the SMMU is perfect and sees nothing" against "the SMMU is lying".
Forcing all three streams to FAULT and running glxgears decided it: `sGFSR` became
`0x80000001` - an invalid-context fault - so GPU traffic **does** reach the SMMU.
But `/proc/interrupts` still showed zero on both fault lines.

**Bug one: the fault interrupts were never delivered**, so every fault this hardware
raised was invisible. Clearing the status and rerunning caught the real one:

    cb1 FSR 0x00000004  FAR 0x01001000  FSYNR0 0x00000582

An **access flag fault**, on the ringbuffer, on every fetch. `CFCFG` is clear, so each
faulting transaction was terminated silently and the command processor read nothing.

**Bug two: `SCTLR.AFE` does not work on this SMMU.** `io-pgtable-arm-v7s` sets `AP[0]`
- which *is* the access flag once AFE is on - in every descriptor it writes, and the
walk still faults. Clearing the bit by hand on the running system settled it
immediately: `gpu-irq` went from one interrupt ever to **702 in twelve seconds**, and
`last-fence` met `retired-fence` for the first time.

Clearing AFE is not just silencing the fault, it also produces the permissions the
mappings asked for. v7s always sets `AP[0]`, so with AFE off the encodings become
`AP[2:0] = 0b011` for a writable page and `0b111` for a read-only one - which is
exactly right, and incidentally explains why the ringbuffer's descriptor differs from
the fence page's: `msm_ringbuffer_new` asks for `MSM_BO_GPU_READONLY`.

The interrupt numbers took two attempts and the first one was wrong, which is worth
recording because of *why* it was wrong.

`arm-smmu` indexes the context interrupt list by `CBAR.IRPTNDX`, not by context bank
number, and on SMMUv1 it hands out `IRPTNDX` round-robin starting at 1. The hardware
raises a bank's fault on **SPI 240 + IRPTNDX**, so the list has to begin at 240 even
though index 0 is never assigned. With the global fault on **SPI 38**, the node wants:

    interrupts = <GIC_SPI 38  IRQ_TYPE_LEVEL_HIGH>,   /* global */
                 <GIC_SPI 240 IRQ_TYPE_LEVEL_HIGH>,   /* IRPTNDX 0 */
                 <GIC_SPI 241 IRQ_TYPE_LEVEL_HIGH>,   /* IRPTNDX 1 */
                 <GIC_SPI 242 IRQ_TYPE_LEVEL_HIGH>;   /* IRPTNDX 2 */

The first attempt read the GIC's pending set with a fault latched and concluded 37 for
the global and 241 upwards for the contexts. The context half was off by one and the
global was simply another device's line - SPI 37 was *already* pending before any
fault was injected, with `sGFSR` reading zero, and that anomaly should have been
enough to reject it.

Off by one is worse than the original bug rather than better. The fault arrives on a
line bound to a *different* bank, whose handler reads a clean `FSR` and returns
`IRQ_NONE`; the level-triggered line then storms until the kernel gives up with
`irq 63: nobody cared` and disables it.

What settled it was unpacking downstream's device tree out of the LineageOS
`boot.img` QCDT container - its `kgsl_iommu` lists global 38 and SPI 241 for all three
contexts - and then letting the hardware arbitrate between that and the measurement.
With context bank 1 alone latching a translation fault and bank 0 idle as a control,
`CBAR(1)` read `IRPTNDX 2` and SPI 242 alone went pending. So downstream's 38 is
right, its 241-for-everything is only accidentally right for whichever context lands
on index 1, and the rule is 240 + `IRPTNDX`.

Delivery is now verified rather than assumed, which the first attempt never was: with
no faults left to raise, zero on a fault counter proves nothing. Forcing `SCTLR.AFE`
back on for bank 1 manufactures an access flag fault on demand, and it comes out the
whole way - the bank's own line increments, the handler clears `FSR` instead of
storming, and drm/msm prints the faulting address:

    *** fault: iova=         1001000, flags=0

`0034` and `0035` carry both fixes. **The GPU now renders through its IOMMU.** A
three-minute glxgears soak gives zero hangchecks, 55,145 GPU interrupts, fences
retiring within three of submission, and no fault on any line.

It is still out of the default build, for a reason that is now a measurement rather
than a suspicion. Like-for-like at 320MHz with `vblank_mode=0`:

| kernel | glxgears | hangchecks |
|---|---|---|
| r56, carveout, no IOMMU | 780 FPS | 0 |
| r66, GPU behind the SMMU | 154 FPS | 0 |

A five-fold cost, for no reclaimed memory at all until the **MDP** has an IOMMU too -
see below.

**Where the cost goes is now measured, and it is translation itself.** In five seconds
of load there are *zero* calls to `arm_smmu_map_pages`, `unmap_pages`, `iotlb_sync`,
`tlb_inv_*` or `runtime_resume` - the only thing firing is `msm_gem_vma_map`, 33784
times, every one of them returning early on `vma->mapped`. So there is no maintenance
in steady state at all. glxgears drops from 94.5% of a core to 26.7%, meaning it is
blocked on the GPU rather than on the CPU. And throughput scales inversely with pixel
count - 866 FPS at 64x64, 335 at 200x200, 89 at 400x400 - where 64x64 reaches the same
CPU-bound ceiling as the carveout kernel. The SMMU adds no fixed per-frame cost
whatsoever; it adds a cost to every memory access, which is what TLB misses walking
uncached page tables look like.

Runtime PM is ruled out by direct A/B: pinning `power/control` to `on` gives
153.887-153.951 FPS against 153.884-153.951 on `auto`.

**`dma-coherent` is not the answer, and the hardware lies about it.** `IDR0.CTTW`
reads 1, and the driver only treats the walk as non-coherent because the node lacks
the property - it says so, `(IDR0.CTTW overridden by FW configuration)`. Adding it
makes the driver report `coherent table walk` and leaves `TTBR0` cacheable, and the
GPU then produces no frames at all: glxgears never prints, hangchecks climb, and both
fault lines storm. The interconnect is not coherent with the CPU, so the walker reads
stale descriptors. The driver's own comment warns about exactly this - trust the
firmware description over the ID register - and this SoC is the case it means.

**Page size was the answer, and `0036` is worth three times the throughput.** Every
mapping used to be a 4KB small page, because `msm_gem_vma_init()` allocated IOVAs with
`PAGE_SIZE` alignment and `iommu_pgsize()` can only fold a mapping into a larger page
when the IOVA *and* the physical address share that alignment and the size covers it.
`pgsize_bitmap` is `0x41311000`, so 64KB and 1MB were available and unreachable.

`0036` asks for the largest page an object can fill, at both ends - the IOVA allocator
and the VRAM carveout allocator - since aligning only one of them changes nothing. It
costs no memory worth naming: `drm_mm` places an aligned node in the first hole that
fits rather than padding, so the skipped space stays available to smaller objects, and
the carveout base is already 1MB-aligned at `0x70100000`.

Confirmed in the page tables rather than inferred from the frame rate. Walking context
bank 1 during a run now finds **7 sections of 1MB and 92 large pages of 64KB**
alongside 366 small ones, where before there was nothing but small ones - about 465
TLB entries covering what used to need roughly 3600.

Like-for-like, `vblank_mode=0`, GPU pinned at 320MHz. Note the carveout kernel is
CPU-bound at every size here, which is why its numbers barely move:

| window | carveout | IOMMU, 4KB pages | IOMMU, `0036` |
|---|---|---|---|
| 200x200 | 855 FPS | 340 FPS | 876 FPS |
| 300x300 | 783 FPS | 154 FPS | 511 FPS |
| 400x400 | 834 FPS | 88 FPS | 276 FPS |

So the gap at the default size falls from 5.1x to **1.53x**, and at 400x400 from 9.5x
to 3.0x. A 150 second soak at 300x300 gives zero hangchecks, zero faults on any line,
and `last-fence` equal to `retired-fence` at 264505.

What is left of the gap is the 366 small pages and the irreducible cost of translating
at all. Still out of the build, but the trade is now arguable rather than obviously
bad - and it buys the GPU real memory protection, which the carveout cannot.

One honest loose end: `msm8974_smmu_write_s2cr` forces `NSCFG` and `MEMATTR` because
downstream does, and it was originally added on a theory - that unmarked transactions
were landing on the secure context banks - which the AFE finding disproves. Whether
the hardware needs it has never been tested on its own.

Two register facts settled along the way, both from downstream's `iommu_hw-v1.h`.
`0x2000` is `MICRO_MMU_CTRL` with halt-request at bit 2 and idle at bit 3, so the
earlier suspicion of the prior art's offsets was misplaced - and `INTR_SEL_NS` does
not exist on this SoC at all, which means mainline's `writel(0xffffffff, 0x2000)` is
writing all-ones into the halt control register. That is a real latent bug, though
measurement shows it is not this one: `MICRO_MMU_CTRL` reads `0x00000008` on entry,
idle and unhalted, and clearing halt-request explicitly changes nothing. Downstream
never halts these instances either - `qcom,iommu-enable-halt` appears zero times
across all ten of them.

## The MDP IOMMU, and the 192MB

`msm_use_mmu()` tests `device_iommu_mapped(dev->dev) || device_iommu_mapped(dev->dev->parent)`,
where `dev->dev` is the *display controller*. The carveout is gated on the **MDP**
having an IOMMU, not the GPU, so a flawless GPU IOMMU reclaims nothing by itself.

`0037` adds `mdp_smmu@fd928000` and points the MDP at it, and **the carveout is
gone**: no `using 192m VRAM carveout`, no `VRAM: 70100000->7c100000`, the display
controller bound to `smmu.0xfd928000`, `FD330` still the renderer, and zero faults on
any of the six interrupt lines the two SMMUs now register.

Three things made it much cheaper than expected. It is the **same hardware as the
GPU's SMMU** - identical probe, 4 stream-match groups, 3 context banks, and the
`numpage` write-back test reading `0xdeadbee0` at `+0x8000`, which agrees with stock
placing `mdp_0` at `0xfd930000`. So `0034`/`0035`'s compatible and quirks carry over
and **no new driver code was needed**. Stock and LineageOS describe both IOMMUs
identically, so the vendor tree could be trusted here. And despite
`qcom,iommu-secure-id = <1>`, **TrustZone does not block the non-secure side** -
`arm-smmu-qcom` never calls `qcom_scm_restore_sec_cfg` and does not need to.

The trap worth recording: this SMMU sits in the display's path whether or not anything
attaches to it, and `arm_smmu_device_reset()` rewrites every S2CR *before*
`impl->reset` runs. With `CONFIG_ARM_SMMU_DISABLE_BYPASS_BY_DEFAULT=y` that blanks the
panel just by probing. **Boot with `arm-smmu.disable_bypass=0`** - MDSS has masters
that are not described here, and they still have to get through.

**What it costs.** Without the carveout, GEM objects come from shmem as scattered
order-0 pages, so `iommu_pgsize()` cannot coalesce whatever the IOVA alignment is and
`0036`'s gain disappears entirely - its `get_pages_vram` half becomes dead code.
Walking both SMMUs afterwards finds **no sections and no large pages at all**, only
4253 small pages on the GPU and 1945 on the MDP. Throughput goes back to the 4KB
figures: 329 FPS at 200x200 against 876 with the carveout.

| | carveout (r56) | MDP IOMMU (r74) |
|---|---|---|
| `CmaFree` | 65152 kB | 261760 kB |
| glxgears 200x200 | - | 329 FPS (876 with carveout) |

`CmaFree` is the honest number: exactly 192MiB handed back. Net usable memory gains
less than that, because the display and GPU buffers now come out of ordinary memory
instead of a reservation - about 24MB of them were mapped during a run.

Shmem huge pages would fix the page size and give both, but they are not reachable
here: `HAVE_ARCH_TRANSPARENT_HUGEPAGE` is selected only `if ARM_LPAE`, and LPAE is off
- which is also why the IOMMU uses the v7s short-descriptor format. Getting large
pages back alongside the reclaimed memory would mean a CMA-backed GEM allocator rather
than shmem, which is a real divergence from upstream.

**`0037` is not finished: the panel goes black.** It was briefly turned on by default
and that was wrong. Everything the console can see says the display works - `fb0`
registers, the backlight is lit, `glxinfo` reports `FD330`, glxgears runs at 151 FPS
with `last-fence` equal to `retired-fence`, and no SMMU raises a fault - and the
screen still shows nothing. None of those checks touch scanout, which is the one path
`0037` changes: the line that disappears when the MDP attaches is precisely
`no IOMMU, fallback to phys contig buffers for scanout`.

**The fault is on the page-table walk, not on the display's reads.** Booting with the
bypass *enabled*, so that anything unmatched faults loudly, gives:

    cb1 FSR 0x00000010  FSYNR0 0x00000581  FAR 0x00001000

`FSR` bit 4 is EF, an external fault rather than a translation fault, and `FSYNR0`
bit 10 is **PTWF** with `PLVL` 1: the abort happened while the SMMU was fetching the
**level-1 descriptor**, on a read, non-secure. `sGFSR` is zero throughout, so no
stream went unmatched - which kills the obvious theory that MDSS has a master we have
not described.

The display is not failing to read its framebuffer. **The SMMU cannot read its own
page tables.** Walking those tables by hand from the CPU works perfectly -
`iova 0x1000` resolves to `PA 0x30291000`, ordinary System RAM with real content in
it - which is exactly the trap: the CPU can reach that memory and the MDP SMMU's
table-walk master cannot. Four attempts were aimed at the wrong transaction before
this was measured.

Three theories tested and dead, each on hardware:

- **An unmapped MDSS stream.** `sGFSR` is 0 with `USFCFG` set, so nothing is going
  unmatched.
- **The TrustZone handover.** `mdp_iommu` carries `qcom,iommu-secure-id = <1>` and the
  GPU's does not, so `qcom_scm_restore_sec_cfg()` - which `qcom_iommu.c` has always
  called for this hardware - looked compelling. It is actively harmful here. Called
  from `cfg_probe` it collapses the stream ID mask to zero, because
  `arm_smmu_test_smr_masks()` runs afterwards and derives the mask by writing an SMR
  and reading it back; the MDP then loses its IOMMU entirely with
  `stream ID 0x1 out of range for SMMU (0x0)`. Called per context at attach instead,
  the phone runs about two minutes and then dies with mmc timeouts and an RCU stall.
  Sony's TrustZone uses the legacy SCM convention and does not mean by that call what
  `qcom_iommu.c` expects.
- **The BFB settings.** Downstream programs 18 implementation-defined registers on
  this instance against 12 on the GPU's, with `0x204c` at `0xffffffff` rather than
  `0x3`. `0038` applies stock's table verbatim from the reset hook, they read back
  correctly, and the fault is bit-for-bit identical.

So the open question is narrow and worth stating precisely: **why can this SMMU's
table-walk master not read normal memory, when the GPU's identical SMMU can?** Both
tables live in the same low physical range and the GPU's instance walks them happily.
The remaining differences are the clocks, the power domain, and the NoC path.

`0034` through `0038` stay out of the build.

**And the process lesson, which cost more than the bug.** This was declared working
and *flashed as the default kernel* while the panel showed nothing but backlight.
`fb0` registering, `bl_power`, `glxinfo` reporting `FD330`, glxgears at 151 FPS with
`last-fence` equal to `retired-fence`, and zero faults on every line - every one of
those passed, and not one of them tests scanout. A display change is verified by
looking at the panel and by nothing else.

The lesson is worth more than the patch. A display change is not verifiable from the
console. `fb0`, `bl_power`, `glxinfo` and a frame counter are all proxies that pass
while the screen is black; only looking at it counts.

It went unsolved for a long time partly because upstream has not solved it either:
Matti Lehtimaki's `qcom-msm8974-5.19.y-iommu` branch is, in Luca
Weiss's words on the freedreno list, "a semi-working branch but hitting random
issues with it". One thing worth keeping from reading it - the `#if 0` block of
register pokes in that branch is not guesswork, it is downstream's
`qcom,iommu-bfb-regs`/`-data` pair for `kgsl_iommu` verbatim, which is the
non-secure init the GPU IOMMU needs.

Where the port goes next is in `next-steps.md`.

## Audio

*Since this was written a WCD9320 driver exists in the series (`0050`-`0068`): the
codec probes and every register works, but no data moves over SLIMbus in either
direction, so there is still no sound. The fault is in the port engine. See
`worklog.md`, "Phase 3: audio".*

The codec is a **WCD9320 (Taiko) on SLIMbus** - stock's tree calls it `taiko_codec`,
`compatible = "qcom,taiko-slim-pgd"`, with the bus at `slim@fe12f000` (`qcom,slim-ngd`)
and a card called `qcom,msm8974-audio-taiko`.

Mainline has the APR transport, the whole Q6 stack, the SLIMbus core and two SLIMbus
controllers. **It does not have a WCD9320 driver** - the codecs in tree are wcd9335,
wcd934x and wcd937x/938x/939x, all later parts. Nothing makes sound without that
driver, and writing it is the bulk of the work.

`0039` does the part underneath it: an `apr` node on the ADSP's existing `smd-edge`,
the same edge the sensor manager already uses, with `q6core`, `q6afe`, `q6asm` and
`q6adm`. The ADSP is enabled on rhine and reports `running`, so the transport should
come up; `q6core` reporting the ADSP's version is the check. It produces no sound by
itself.

SLIMbus is the middle step and needs a compatible of its own: stock calls this
controller NGD, but mainline's NGD driver knows only `qcom,slim-ngd-v1.5.0` (8996) and
`-v2.1.0` (SDM845), with a separate non-NGD driver for apq8064. msm8974 sits between
them.

## Battery temperature, and why the jeita band had to be widened

`0024` sets `qcom,jeita-extended-temp-range`, and that turns out to be the correct
setting for this battery rather than a workaround.

The PM8941's battery temperature comparator comes with two fixed windows, expressed as
percentages of the thermistor's reference: [35%:70%] or [25%:80%]. Calibrating the
VADC from its own `REF_625MV`, `REF_1250MV` and `GND_REF` channels gives 97.37
uV/count, and against `VDD_VADC` at 1781.7 mV the thermistor reads:

| | raw | mV | % of reference |
|---|---|---|---|
| at rest | 30949 | 606.5 | 34.0% |
| after ten minutes of four-core load | 30499 | 562.7 | 31.6% |

**606.5 mV is already below the narrow band's 35% floor of 623.6 mV**, so that window
inhibits charging at ordinary room temperature - permanently, not marginally. The
extended window's floor is 25%, or 445.4 mV.

The load moved it 43.8 mV for a 7.1 C rise in PMIC die temperature, about -6.2 mV/C,
and `BAT_THERM` kept falling for a while after the CPU started cooling, so the battery
warmed by less than that and the true slope per battery-degree is steeper. Either way
there is 26 C or more of headroom before the extended hot threshold trips, putting it
somewhere near 50 C, which is about where charging should stop anyway.

The reason a normal reading sits so low is that those thresholds are sized for
Qualcomm's reference battery and amami's thermistor is not it. Worth knowing on top:
**mainline has no `SCALE_BATT_THERM`**. Downstream declares this channel with
`qcom,scale-function = <1>`, a dedicated battery-thermistor table; mainline offers only
`DEFAULT`, `THERM_100K_PULLUP`, `PMIC_THERM`, `XOTHERM` and the HW_CALIB variants.
That is why `LR_MUX1_BAT_THERM` has no `_input` attribute and why `qcom_smbb` reports
no battery `temp` at all.

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

## Camera

The rear camera now delivers real frames through mainline CAMSS, though the image
still needs lens-shading and colour work, and the front camera has not been started. The full history, including the
wrong turns, is in `worklog.md` under "Camera".

**CAMSS.** msm8974's camera block is the same generation as msm8916's, which mainline
supports: identical register offsets, a different base (0xfda00000) and more
instances (3 CSIPHY, 4 CSID, 2 VFE). `0085`-`0087` add it. It depends on `IOMMU_DMA`,
which arm32 cannot select, so `debug/9006` drops that for bring-up, and without an
IOMMU the VFE needs contiguous buffers (`debug/9010`, CMA). The media config must be
modular; built in, it stops the kernel booting.

camss sizes its clocks too low for msm8974. The CSID rule assumes four bytes a
clock and the VFE raw-dump rule eight, which gives 100 and 50 MHz for a four-lane
576 Mbit/s stream. Built separately, each half failed: a fast VFE behind a 100 MHz
CSID still corrupted every frame, a 200 MHz CSID in front of a 50 or 80 MHz VFE
delivered no frames at all, and only both at 200 MHz worked. Both blocks behave as
16-bit paths, which is what `0099` sizes them for.

**The sensors**, read off the chips and the module EEPROMs rather than guessed:

    rear   Sony IMX200  module SOI20BS0  CCI 0, 0x10  CSIPHY0, 4 lanes  AF: BU64296G
    front  Sony IMX132  module SEM02BN1  CCI 1, 0x36  CSIPHY2, 2 lanes  no AF

Both are SMIA-family parts, so they run on mainline's generic CCS driver
(`nokia,smia`). That driver needed six fixes before the IMX200 would stream:
`0091` ignores CCS-only limit registers that hold junk on SMIA++ parts, `0092` and
`0093` repair sub-device state the 6.16 conversion broke (the binner and pixel array
had 0x0 formats, and crops never reached the formats), `0094` identifies the IMX200
and gives it the per-lane PLL model, `0095` stops camss starting the sensor twice
(which rewrote the PLL mid-stream and wedged its I2C), and `0096` fixes the helper all
quirk register tables go through.

**The MCLK can't make 24 MHz.** msm8974's camera clock RCGs have no M/N counter, so
24 MHz quietly became 120 MHz; `0090` lists only the rates they can make, and the
sensors run from 19.2 MHz.

**What made real frames appear came from the stock firmware.** Sony's per-module file
`/system/vendor/camera/SOI20BS0_IMX200.dat` holds the register tables the stock
camera stack writes: an 87-register init table of manufacturer registers, 18
per-mode tables, and small ones for streaming, reset, orientation and test patterns.
`tools/unsin.py` gets the system image out of the FTF and `tools/semcdat.py` dumps the
tables. `0098` writes the init table and mode 0's readout window registers from the IMX200
quirk at power-on; without the window registers the pixel array reads pure black.
(`debug/9013`, out of the build, is the harness that found this: it writes the stock
tables in groups chosen by a module parameter.)

**Three things about the link that took finding:**

- RAW8 cannot work. In 8-bit the sensor sends its lines as data type 0x30, which the
  CSID drops. Use RAW10.
- camss computes a CSIPHY settle count of 11 for the 288 MHz link; the line data is
  clean from about 9 down, but the frame-start packets only come through at 2 or 1.
  At 3, every other frame starts in the wrong place, which shows up as a horizontally
  shifted band in the picture. Measured in time it is the same at a 200 MHz PHY
  timer: frame starts need a settle of about 35 ns or less, line data syncs up to
  about 125 ns. `0097` lets the board set the settle time (`qcom,hs-settle-ns` on the
  CSIPHY endpoint), and amami sets 30 ns.
- Stock mode 0's clock registers (0x3004/0x3005/0x9229) change the sensor's lane
  timing so that nothing syncs; they stay off. Where stock programs the PLL is still
  unknown: the stock kernel's camera driver only handles power and the EEPROM, so it
  lives in Sony's userspace.

**Working recipe** (`tools/camera/capture.sh`): RAW10 at 288 MHz, exposure up to
3976 lines, analogue gain around 128. Nothing is poked at run time any more. The module is mounted
sideways, so the picture needs rotating 90 degrees clockwise. After a stream that fails
or times out, the next start wedges camss and sometimes resets the phone; after good
ones, six streams in a row in one boot worked. The frame rate follows the exposure: about
6.7 fps at 3976 lines, 16.8 fps at 1200.

**Focus: a ROHM BU64296GWX at 0x0c on CCI master 0, powered by l23 (2.8 V).** Stock has
no enable GPIO for it (`sony,gpio_af = 0`) and switches l23 on after VANA. The protocol is
in `libcammw` (`focus_bu64296gwx_vcm`, write helper around 0x10dd0): two-byte transfers,
and a lens position is `0xc4 | pos[9:8]`, `pos[7:0]`. Stock also writes 0xcc (a mode, the
low three bits of a `.dat` parameter) and 0xd4 (a timing value) at init; plain position
writes work without them. `0101` is a driver in the style of `dw9714`
(`V4L2_CID_FOCUS_ABSOLUTE`, 0-1023, powered while its subdev is open) and `0102` adds it
to the device tree with `lens-focus` on the sensor. Higher values focus closer. Through a
window, the city outside was sharpest at 256 and a board just in front at 512;
768 and above is macro range. Sharpness changes by up to three times across the sweep.

**The module EEPROM holds factory lens-shading calibration.** It is 2 KB at 7-bit
0x50-0x57 on CCI master 0 (eight 256-byte pages, one-byte addressing; read it during a
stream so the module is powered). It starts with the module, sensor and actuator names
(`SOI20BS0`, `IMX2000A`, `BU64296G`). From 0x100 come 64-byte blocks, each a 9x7 grid
of relative brightness with 0x80 at the centre, plus one trailing byte. The corners sit
around 0x24, so the lens loses about 70% of its light at the edges. `tools/camera/raw10.py`
averages the nine grids and applies that to every channel. Which block is which channel
is not known, and it barely matters: with the sensor's own correction off, the falloff on a
white sheet is the same in all channels to within a few percent (R/G varies about 5% across
the frame, B/G about 10%, partly from the light itself), and no pairing of blocks explains
those ratios clearly better than no colour correction at all. Blocks 9-11 are flat 0x80.
The bytes around 0x60-0xdf (probably white-balance data) are not decoded.

**How stock clocks the sensor.** `libcammw.so` has the IMX200 parameters built in, in the
same layout as the header of the `.dat` file, and its set-mode routine writes the clocks
itself: the external clock frequency at 0x011e (CCS writes 0x0136, which this sensor
ignores), the dividers at 0x0301, 0x0303, 0x0309 and 0x030b, the pre-divider at 0x0305, one
multiplier at 0x0306 and a second at 0x030c. The values come from a 24-byte record at
`0x104 + 0x90 x mode` in the `.dat` header, except 0x030c, which is the stock device
tree's per-mode `pll` number (600 for full resolution). Stock runs the sensor from an
8 MHz MCLK, which mainline cannot make: the MCLK RCGs have no M/N counter, and their M/N
registers do not take writes even with the clock running. Writing stock's values scaled to
19.2 MHz after CCS's own (`debug/9014`) changed nothing: the registers read back CCS's
values and the frame rate stayed the same.

**Measure the frame rate with the frames going to `/dev/null`.** With `--stream-to` a
file, v4l2-ctl reports about 1.7 fps, which is the phone's storage writing 26 MB frames.
The sensor itself runs at about 6.7 fps at full resolution, against stock's 8.6.

**Brightness is fine.** At night under one lamp the longest exposure filled only a few
percent of the range, which looked like a missing analogue setting. In daylight the same
exposure clips about a fifth of the frame, so it was only dim light.

**The colour blotches were the sensor's own lens-shading correction.** The IMX200 comes
out of reset with 0x0700 (its LSC enable) set to 1 and an uninitialised gain table, which
paints large per-channel blobs over every frame. A white sheet over the lens showed it
clearly. Stock (`libcammw`) only enables it after uploading a table: 0x0700 = 1,
0x4500 = 0x1f, then 16-bit gains for the four channels at 0x4800, 0x4802, 0x48fc and
0x48fe plus 4 x n for n up to 62, then 0x3a63 = 1. `0098` now writes 0x0700 = 0. On the
same white sheet Gr/Gb is then 0.99-1.01 everywhere and R/G and B/G vary by a few percent
across the frame, leaving only the lens's ordinary vignetting.

**The camera now runs on its own driver, `imx200` (`0103`, `0104`).** CCS presents the
sensor as three chained subdevs and cannot enumerate frame sizes, so libcamera could not
use it. `imx200` is a plain single-subdev driver in the style of `imx219`: stock's init
table, the PLL that CCS arrived at from 19.2 MHz, and four of stock's modes with their
register tables. Things it had to learn:

- Writes made within a few milliseconds of releasing reset are lost; it waits 20 ms.
- **Starting the stream resets the readout registers** (binning, window, output size)
  to full resolution. Read back 50 ms after `0x0100 = 1`, `0x0391` had gone from 0x22 to
  0x11. Written after stream-on they hold, so the driver writes the mode then; the first
  frame or two of a binned stream still come out at full size. Restarting the stream to
  avoid that reset the phone.
- Measured line times: 14.93 us at full resolution and 10.11 us in every binned mode, so
  the pixel rate is 395.5 MHz or 583.9 MHz. Frame rates: 16.8 fps at 5248x3936, 48.8 at
  2624x1976, 64.7 at 2624x1480 and 95.9 at 1312x988.
- **Lens shading on the sensor, as stock does it.** `libcammw` uploads 63 16-bit gains
  per channel (8.8 fixed point, so the 9x7 grid exactly) to 0x4800 and 0x48fc, two
  channels interleaved in each, then sets 0x0700 = 1, 0x4500 = 0x1f and 0x3a63 = 1. The
  driver reads the EEPROM at probe, averages its nine grids and does the same.
- **The EEPROM also holds focus calibration**, big-endian at 0xd0: 326, 359 and 681,
  which look like infinity, a middle distance and macro. `0102` rests the lens at 359
  (`rohm,default-position`), because nothing autofocuses yet.

**libcamera.** With `imx200`, libcamera's simple pipeline and software ISP take the
camera, and PipeWire offers it to applications as "Built-in Back Camera". GNOME
Snapshot shows a live preview, upright thanks to the `rotation` property. What it took
(`recipe/libcamera`):

- `0004` adds the IMX200 gain model (256 / (256 - code)), black level 64, pixel size and
  control delays. `imx200.yaml` carries the colour matrix from stock's
  `SOI20BS0/color_ctrl.dat`: int16 in Q10, the only non-identity matrix in the file.
- `0005` fixes two colour bugs in the CPU debayer. The black level was subtracted after
  the white balance gains and the colour matrix, which lifted red and blue and turned
  every shadow magenta. And white balance was folded into the matrix with no clip in
  between, so clipped highlights came out pink.
- `0006` leaves saturated pixels out of the white balance sums. With a bright window in
  the frame they pulled the gains towards none and left the room green.
- The GPU debayer cannot work: msm refuses to import other drivers' buffers without its
  IOMMU (`cannot import without IOMMU`). `/etc/libcamera/configuration.yaml` selects the
  CPU one, which manages about 20 fps at 1280x960 on four cores.
- libcamera allocates from the DMA heaps (`CONFIG_DMABUF_HEAPS`). The CMA heap is left
  root-only by `userspace/50-dma-heap.rules`: the GPU's VRAM carveout takes most of CMA,
  and libcamera would try it first and fail on large frames.
