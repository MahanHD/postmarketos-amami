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

`s2idle-test.sh` measures suspended draw on a phone with no coulomb counter. It
runs an awake window with the IADC sampled directly, then an `rtcwake` suspend of
the same length, and reads both endpoints at the *same* load state - awake, screen
off, after a settle - because `capacity` and `voltage_now` here follow load rather
than charge. It samples *through* each settle so the flattening can be checked
instead of assumed, which matters: the run in
`docs/measurements/s2idle-2026-09-14/` had its scripted end-of-suspend snapshot
land on a current spike, and the matched-load row from `settle.csv` had to be used
instead. Copy it to the phone and run it there; the USB cable has to be **out**.

    scp tools/s2idle-test.sh mahan@<phone>:/tmp/
    ssh mahan@<phone> 'sudo systemd-run --unit=s2idle /tmp/s2idle-test.sh'

`ff-test.py` drives a force-feedback device, which is the only way to tell a
motor that works from one that merely enumerates - an ff-memless device appears
in `/dev/input` whether or not anything is wired to the output it drives. It
scans for the node advertising `FF_RUMBLE`, uploads an effect and plays three
bursts at different magnitudes. Run it on the phone; it needs no compiler there.

    scp tools/ff-test.py mahan@<phone>:/tmp/
    ssh -t mahan@<phone> 'sudo python3 /tmp/ff-test.py'

The reason it packs its own structs rather than leaning on a library:
`sizeof(struct ff_effect)` is **44** on arm32, not 40, and `EVIOCSFF` encodes
that size in the ioctl number (`0x402c4580`), so a wrong guess returns `EFAULT`
and reads like a driver bug. The script asserts its own packing.

`qrtr-services.py` lists every QMI service advertised over QRTR, by node. It
exists because the SLIMbus NGD controller waits for QMI service `0x301` from the
ADSP and waits *silently* - so an empty `/sys/bus/slimbus/devices/` with nothing
in dmesg cannot, on its own, tell "the service is missing" from "the driver is
broken".

    scp tools/qrtr-services.py mahan@<phone>:/tmp/
    ssh mahan@<phone> 'sudo python3 /tmp/qrtr-services.py'

**It self-tests before it reports anything**, by publishing a fake service and
checking that its own lookup finds it. That is not ceremony. The first version
of this script guessed the command numbers - `NEW_SERVER` and `NEW_LOOKUP` are
**4** and **10** in `include/uapi/linux/qrtr.h`, not 2 and 7 - so it sent `HELLO`
and `RESUME_TX`, received nothing, and reported a confident zero services. That
got as far as being written up as "the ADSP advertises nothing" before the
self-test showed the probe could not see a service published one line earlier.
With the right constants the same phone reports 36 services, `0x301` among them.

There is no known-good QMI service here to validate against - wcn36xx talks
`WCNSS_CTRL` over SMD, not QMI - which is exactly why the script has to
manufacture one.

Two more details that cost time. `bind()` rejects any node but the local one, so
`(0, 0)` is not a wildcard; the script probes for it and the answer here is node
1. And a listing ends with an all-zero `NEW_SERVER` as a terminator, so filtering
those out - as the first version did - throws away the one packet that
distinguishes "the list is empty" from "nothing replied".

`smgr-info.py` and `smgr-probe.py` talk to the ADSP's sensor manager directly over
QMI/QRTR, so a sensor question can be answered without a kernel build, a flash and
a reboot per attempt. SMGR is QMI service `0x100` and the kernel driver binds at
node 5 port 6; unload `qcom_smgr` first so the two are not both subscribing.

    ssh mahan@<phone> 'sudo modprobe -r qcom_smgr_prox qcom_smgr_accel \
        qcom_smgr_gyro qcom_smgr_mag; sudo modprobe -r qcom_smgr'
    ssh mahan@<phone> 'sudo python3 /tmp/smgr-info.py 0x28'   # what a sensor is
    ssh mahan@<phone> 'sudo python3 /tmp/smgr-probe.py'       # subscribe and watch

`smgr-info.py <id>` prints each data type with its max rate, current draw, range
and resolution - which is how proximity and ambient light were told apart on the
APDS-9930, since both carry the same name string. The current draw gives it away:
`data_type 0` pulls 12675 uA (the IR LED) and `data_type 1` pulls 175 uA.

`smgr-probe.py` runs subscription trials. **It filters indications by `report_id`
and settles after each DELETE**, which is not optional: an earlier version counted
every `0x22` indication, and with the accelerometer control running at 50 Hz its
stragglers arrived during the next trial's window and were read as proximity data.
That produced a "proximity works" result that was entirely the control leaking.

It also reads `ack_nak` (TLV `0x11`) from the buffering response, which
`qcom_smgr_set_buffering()` ignores - it only checks `result`. Every subscription
to sensor `0x28` is NAKed while the accelerometer is ACKed, and the driver cannot
see the difference.
