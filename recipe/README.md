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

## libcamera

`libcamera/` holds what this port adds to pmaports' `temp/libcamera` (0.7.1):
`0004` (IMX200 gain model and properties), `0005` and `0006` (soft ISP colour fixes),
`0007` (contrast autofocus for the simple pipeline), `0008` (a crash fix), `0009` (a
short list of output sizes) and `imx200.yaml`, the tuning file with the focus range
(stock's colour matrix is in it, switched off for speed). The `APKBUILD` there is the
complete one, with all nine patches and the tuning file in its source list.

## mesa

`mesa/` is Alpine 3.24's `main/mesa` (26.1.6) with one fix for this GPU,
`freedreno-a3xx-end-direct-loads.patch`: every direct `CP_LOAD_STATE` is followed by a
register write, as the stock driver does on a3xx. Without it GTK4's GL renderer hangs the
Adreno 330 within seconds (see `../docs/notes.md`, "The GPU hang, solved"). Two build
changes go with it: rusticl is off on armv7, since pmbootstrap's cross build has no Rust,
and clang, libclc and the SPIR-V translator are top-level makedepends, because
pmbootstrap does not read the `case` blocks that add them. Build it from pmaports'
`temp/mesa` with `pmbootstrap build mesa --arch armv7` (about 15 minutes) and install
`mesa`, `mesa-dri-gallium`, `mesa-egl`, `mesa-gbm`, `mesa-gl` and `mesa-gles`.

## megapixels

`megapixels/` is Alpine 3.24's `community/megapixels` (2.1.0) with three fixes that make
it use the colour profile correctly: it finds the profile (`dcp-search-each-path.patch`),
applies the colour steps in the right order (`preview-colour-order.patch`), and measures
white balance on the preview as it is (`awb-stats-in-srgb.patch`). See
`../docs/notes.md`, "Megapixels' colour, fixed". Build it from pmaports' `temp/megapixels`
and install it with `userspace/megapixels/*` copied to `/usr/share/megapixels/config/`.

## libmegapixels

`libmegapixels/` is Alpine 3.24's `community/libmegapixels` (0.2.3) with
`rate-through-vblank.patch`: a `Rate` command on a sensor without a frame interval (every
raw sensor in mainline, imx200 included) sets the frame rate through vertical blanking.
Without it Megapixels' auto exposure stops at the sensor's default frame length.
