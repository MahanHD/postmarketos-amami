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
