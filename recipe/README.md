# Kernel recipe

`APKBUILD` and `config-postmarketos-qcom-msm8974.armv7` are the
`linux-postmarketos-qcom-msm8974` package from pmaports (v26.06) as this port
builds it: kernel 6.16.12 from `msm8974-mainline/linux`, the patches from
`../patches` (and the ones from `../patches/debug` that are listed), and the
config with the changes the port needs.

To build it, copy both files into
`pmaports/device/testing/linux-postmarketos-qcom-msm8974/` together with every
patch the `source=` list names, then:

    pmbootstrap checksum linux-postmarketos-qcom-msm8974
    pmbootstrap build linux-postmarketos-qcom-msm8974 --arch armv7

The recipe also needs `a330_pm4.fw` and `a330_pfp.fw` next to it. They are the
Adreno 330 microcode from linux-firmware (`qcom/a330_pm4.fw`,
`qcom/a330_pfp.fw`) and are built into the kernel, because the GPU probes from
the initramfs before `/lib/firmware` exists. They are not in this repository.

The media/camera options must stay modular (`=m`); built in, the same symbols
stop the kernel booting on this phone. See `../docs/building.md` for flashing
and the boot image.
