# Tools

`convert_cmds.py` turns Sony's downstream MDSS DSI command blobs into
`mipi_dsi_*_write_seq_multi()` calls. The vendor format packs each command as

    dtype, last, vc, ack, wait, dlen_hi, dlen_lo, payload[dlen]

with `wait` being a delay in milliseconds afterwards. The script picks DCS or
generic writes based on the MIPI data type and keeps every delay as
`mipi_dsi_msleep()`.

`gen_all_variants.py` does the same thing but emits one C function per panel
variant in `dsi-panel-amami.dtsi` (default, JDI, AUO, AUO new id).

Neither script ships Sony's device tree. Grab it from their GPL release:

    C=2134cafba220b32c43701368413ee333b41b7fe0
    curl -O "https://raw.githubusercontent.com/sonyxperiadev/kernel/$C/arch/arm/boot/dts/qcom/dsi-panel-amami.dtsi"

`mkbootimg.py` builds a boot image S1Boot will take - header v0, 2048-byte pages,
zImage with the amami dtb appended, and the command line this port depends on.
`boot-deploy` writes its own image with a `quiet splash plymouth...` command line, so
anything being tested has to be assembled by hand. Rebuilding r56 with it produced a
byte-identical copy of what was on the boot partition, which is the check to repeat if
a future image ever misbehaves.

The initramfs has to come from the phone rather than the apk, and *after*
`apk add`, since installing regenerates it:

    ssh mahan@<phone> 'cat /boot/initramfs' > initramfs

`romdtb.py` extracts downstream device trees from a stock or LineageOS image and
prints nodes from them, with no need for `dtc`. It is how the GPU and MDP IOMMU
nodes, the audio inventory, the camera bindings and the `batt_therm` scaling were all
recovered without vendor source.

    unzip -p lineage-*.zip boot.img > boot.img
    tools/romdtb.py extract boot.img -o dtb/
    tools/romdtb.py show dtb/dtb-0.dtb fd928000

Stock needs two unwrappings first - the download is a zip holding an `.ftf`, which is
itself a zip of `.sin` files:

    unzip -p D5503_*.zip '*.ftf' > fw.ftf
    unzip -p fw.ftf kernel.sin > kernel.sin
    tools/romdtb.py extract kernel.sin -o dtb-stock/

Prefer stock where it matters: LineageOS descends from Sony's GPL tree but drifts,
while stock pairs with the TrustZone image the phone actually boots. And treat either
as a source of candidates rather than truth - stock lists SPI 241 for all three GPU
context banks, which is only correct for whichever one lands on `IRPTNDX` 1.
