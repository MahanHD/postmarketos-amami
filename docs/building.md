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

## Afterwards

Two workarounds are needed for a usable system:

    printf 'AllowRiskyCriticalPowerAction=true\nCriticalPowerAction=Ignore\n' \
        >> /etc/UPower/UPower.conf

    nmcli radio wifi off
    systemctl mask NetworkManager-wait-online.service

The first stops UPower powering the device off every few minutes because it can't
read the battery. The second saves roughly 110 seconds of desktop startup that's
otherwise spent waiting on WiFi firmware that's going to crash anyway.
