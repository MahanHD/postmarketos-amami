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

Masking `NetworkManager-wait-online.service` used to be necessary here. It isn't
any more, now that WiFi actually connects.

The UPower workaround that used to live here is no longer needed. With `0005` the
battery reports a real percentage, so `/etc/UPower/UPower.conf` can stay at its
defaults, `AllowRiskyCriticalPowerAction=false` and `CriticalPowerAction=PowerOff`.
PowerOff rather than the upstream HybridSleep default, because this device has no
working hibernate to fall back on.
