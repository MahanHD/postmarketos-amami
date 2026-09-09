# Building and flashing

All of this targets postmarketOS v26.06 rather than edge. On edge the
`device-sony-amami` package has been archived and there's no binary for it, while
v26.06 still has it in `device/testing/` with prebuilt armv7 packages.

## pmbootstrap

    pmbootstrap init      # device sony-amami, channel v26.06, UI xfce4

`channels.cfg` sets `recommended=edge`, so you have to pick v26.06 deliberately.

## Applying the patches

Drop them into the kernel aport, add each filename to `source=` in the APKBUILD
and bump `pkgrel`:

    P=~/.local/var/pmbootstrap/cache_git/pmaports/device/testing/linux-postmarketos-qcom-msm8974
    cp patches/*.patch "$P/"
    $EDITOR "$P/APKBUILD"
    pmbootstrap checksum linux-postmarketos-qcom-msm8974
    pmbootstrap build linux-postmarketos-qcom-msm8974

You also need to add `CONFIG_DRM_PANEL_SONY_AMAMI_NOVATEK=y` to
`config-postmarketos-qcom-msm8974.armv7` by hand. A new Kconfig symbol defaults
to `n` and the build won't prompt for it.

The Adreno firmware has to be built into the kernel image rather than loaded from
`/lib/firmware`, because DRM_MSM probes from the initramfs before the rootfs is
mounted and only tries once:

    CONFIG_EXTRA_FIRMWARE="qcom/a330_pm4.fw qcom/a330_pfp.fw"
    CONFIG_EXTRA_FIRMWARE_DIR="firmware"

The blobs come from Alpine's `linux-firmware-qcom`; stage them into
`firmware/qcom/` in `prepare()`.

## Installing

    pmbootstrap install

Then the rootfs goes on by booting TWRP and dd'ing the image to
`/dev/block/mmcblk0p25`, and the boot image to `/dev/block/mmcblk0p14` either
over fastboot or with dd from a running system.

## Iterating on the kernel

Once the device is up, the fastest loop needs no fastboot at all, but it does
need two steps rather than one. `QCOM_SPMI_VADC` and `QCOM_VADC_COMMON` are
modules, and modules come from the rootfs, so writing the boot partition only
updates the built-in drivers. Stale modules load silently, because vermagic
doesn't encode the build number, and a patch touching both a built-in and a
module then appears to be half applied:

    scp linux-...-rNN.apk user@172.16.42.1:/tmp/
    ssh user@172.16.42.1 'sudo apk add --allow-untrusted /tmp/linux-...-rNN.apk'
    ssh user@172.16.42.1 'sudo dd of=/dev/disk/by-partlabel/boot bs=1M conv=fsync' < boot-rNN.img
    ssh user@172.16.42.1 'sudo reboot'

Installing the package also regenerates `/boot/initramfs`, which is worth picking
up, but `boot-deploy` writes its own `/boot/boot.img` with a `quiet splash
plymouth...` command line. Keep `plymouth.enable=0 msm.vram=192m
msm.allow_vram_carveout=1` and build the image yourself.

## Afterwards

WiFi needs two settings, both explained in the README:

    # /etc/NetworkManager/conf.d/98-wifi-powersave.conf
    [connection]
    wifi.powersave = 2

    # /etc/modprobe.d/wcn36xx.conf
    options wcn36xx scan_offload=0

Without the first it associates and then immediately drops the link; without the
second every scan times out. `CONFIG_WCN36XX_DEBUGFS=y` is worth adding to the
kernel config too, since it exposes the firmware capability list that explains
why `0006` is needed.

Bluetooth needs the service from `userspace/`, which gives the controller the
factory address out of the TA partition. Without it bluetoothd reports no
default controller at all:

    sudo install -m 755 userspace/amami-factory-macs /usr/local/bin/
    sudo install -m 644 userspace/amami-bluetooth-mac.service /etc/systemd/system/
    sudo systemctl enable --now amami-bluetooth-mac.service

It needs nothing but python3 and `rfkill`, both already present. Check it with
`bluetoothctl show`, which should report the controller powered on with a
`BC:6E:64:...` address. The README explains where that address comes from.

The same script will give WiFi its factory address, on one named connection so
that other networks keep postmarketOS's randomised default:

    sudo amami-factory-macs wlan "Mahan"

That one is a one-shot, not a service; it edits the connection and stays put.
Expect a new DHCP lease afterwards, because it is a different MAC.

Masking `NetworkManager-wait-online.service` used to be necessary here. It isn't
any more, now that WiFi actually connects.

The UPower workaround that used to live here is no longer needed. With `0005` the
battery reports a real percentage, so `/etc/UPower/UPower.conf` can stay at its
defaults, `AllowRiskyCriticalPowerAction=false` and `CriticalPowerAction=PowerOff`.
PowerOff rather than the upstream HybridSleep default, because this device has no
working hibernate to fall back on.

## Sensors

The gyroscope, magnetometer and proximity sensor hang off the DSP rather than
any I2C bus the application processor can see, so they need two files and no
patches at all.

First the DSP firmware, out of the LineageOS 18.1 zip (see the README for how to
unpack `system.new.dat.br`):

    sudo install -m 644 adsp.mdt adsp.b0? adsp.b1? /lib/firmware/

That alone gets `remoteproc2` booting at every boot. Then the sensor registry:

    sudo mkdir -p /lib/firmware/qcom/sensors
    sudo install -m 644 sns.reg /lib/firmware/qcom/sensors/sns.reg

Check it with `ls /sys/bus/iio/devices/`, which should gain `qcom-smgr-accel`,
`qcom-smgr-gyro`, `qcom-smgr-mag` and `qcom-smgr-prox` about thirty seconds into
the boot. The accelerometer needs `0007`; without it the other three still come
up and it alone is missing.

These drivers are modules, so testing a change to them is a `.ko` swap and a
restart of the DSP rather than a kernel flash:

    sudo cp qcom_sns_reg.ko.zst /lib/modules/6.16.12/kernel/drivers/soc/qcom/
    sudo depmod -a
    echo stop > /sys/class/remoteproc/<adsp>/state
    sudo rmmod qcom_sns_reg && sudo modprobe qcom_sns_reg
    echo start > /sys/class/remoteproc/<adsp>/state

Find `<adsp>` by reading `/sys/class/remoteproc/*/name`, because the numbering
moves between boots.

### Getting sns.reg

There is no copy in any ROM: Android's sensor daemon generates it on first boot.
It is also not in TA, and pmaports ships registries only for sdm845-era devices.
So it has to come off an Android install on the phone itself, and since
postmarketOS lives inside the `userdata` partition, installing Android destroys
it. Back up first:

    ssh phone 'sudo dd if=/dev/mmcblk0p25 bs=4M | gzip -1' > userdata.img.gz
    ssh phone 'sudo dd if=/dev/mmcblk0p14 bs=1M | gzip -6' > boot.img.gz

Then flash TWRP to `FOTAKernel`, LineageOS `system.img` to `system` (2.27 GiB,
unused by postmarketOS) and its `boot.img` to `boot`, all with `dd` from the
running system. `fastboot boot twrp.img` - Volume Up while plugging in the cable
gives the blue LED - then format data, which TWRP will not do to an empty
partition:

    mke2fs -t ext4 -m 0 -L data /dev/block/mmcblk0p25

Boot Android and let it reach the setup wizard; the sensor daemon runs long
before that, so there is no need to complete it. LineageOS builds are
`userdebug` and adb came up already authorised, so no developer options are
needed:

    adb root && adb pull /data/misc/sensors/sns.reg

`dumpsys sensorservice` is worth saving too, since it names the parts.

### Restoring afterwards

Send the image compressed and decompress on the phone. Pushing 12 GB of
uncompressed data through `adb exec-in` corrupted the GPT partition entry array
here - one byte in a partition name, plus a bogus fourth entry - which is enough
that the initramfs, which counts subpartitions with `fdisk` before calling
`losetup`, refuses to boot. Decompressing on the device puts gzip's CRC across
the whole transfer instead. Busybox `nc` in the initramfs is connect-only, so
listen on the host:

    host:  ncat -l 5555 --send-only < userdata.img.gz
    phone: nc 172.16.42.2 5555 | gzip -d | dd of=/dev/mmcblk0p25 bs=1048576

Then restore `boot` the same way and reboot. Verify with `fdisk -l
/dev/mmcblk0p25`, which must show exactly two partitions, both named `primary`.
If boot still stops in the initramfs it exposes a telnet debug shell on port 23.
