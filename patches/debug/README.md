# Diagnostic patches

None of these belong in a build you actually use. They exist because each one
answered a question that could not be answered from the outside, and keeping them
here means the next question of the same shape is cheap instead of expensive.

Add them to the `source=` list in the kernel APKBUILD alongside the numbered
patches. They are numbered from 9000 so they always apply last and never renumber
the real series.

## 9000 - allow writing registers through regmap debugfs

Turns the `#undef REGMAP_ALLOW_WRITE_DEBUGFS` in `drivers/base/regmap/internal.h`
into a `#define`, which makes every regmap register writable from
`/sys/kernel/debug/regmap/*/registers`.

This is how the uneven backlight was settled. Driving WLED string 2 on its own
gave a completely dark panel, which is what an unpopulated string looks like, and
that closed the question as hardware rather than software.

It is a large hole in a running system: anything with a regmap becomes writable
by root, including PMIC rails. Only build it when you are actively poking at
registers, and expect to be able to switch the device off by writing the wrong
one.

## 9001 - serve an extra sensor registry group

Adds `extra_gid`, `extra_offset` and `extra_size` module parameters to
`qcom_sns_reg`, so one registry group can be mapped at load time:

    modprobe qcom_sns_reg extra_gid=2691 extra_offset=0x1700 extra_size=0x100

The offsets in that driver's `group_map` are observed rather than documented, and
Android's sensor daemon does not contain them, so the only way to find the one
the DSP wanted for the accelerometer was to try candidates. This turned each
candidate into a module reload instead of an eight minute kernel build, which is
the difference between an afternoon and a week. It found `0007`.

Worth knowing while using it: bad registry data wedges the sensor manager past
both a module reload and a remoteproc restart, so a wrong guess costs a reboot.

## 9002 - trim the offloaded scan request

Adds `scan_ie_mode` to `wcn36xx`, which trims the variable length IE block off
the end of `START_SCAN_OFFLOAD`:

    0 - send the IEs as usual          (593 bytes here)
    1 - no IEs, keep the ie_len field  (471 bytes)
    2 - no IEs and no ie_len field     (469 bytes)

Written to test whether the firmware was rejecting the request on length. It was
not - all three were ignored identically - and that ruled out a whole family of
guesses in a single build. The answer turned out to be a capability bit, `0010`,
found by reading Qualcomm's prima and the upstream patch history rather than by
staring at the wire.

Kept because "does the firmware care about the length of this message" is a
question that will come up again.

## 9003-9005 - GPU, IOMMU and suspend probes

`9003` logs each a3xx GPU init step, `9004` dumps the SMMU context bank state, and
`9005` dumps the MPM's vMPM enable masks at suspend. Each answered one question in the
GPU IOMMU and deep suspend work. None of them is in the build.

## 9006 - CAMSS on arm32

`VIDEO_QCOM_CAMSS` depends on `IOMMU_DMA`, which 32-bit ARM cannot select. This drops
the dependency so the driver can be built for bring-up. Real use wants the CAMSS IOMMU.

## 9007 - describe both cameras

Adds both sensors to amami's device tree as `nokia,smia` (the generic CCS driver), with
their regulators, MCLKs and reset lines. The rear one is linked to CSIPHY0; the front
one is left unlinked until its driver quirk exists, because CAMSS waits for every linked
sensor before registering anything.

## 9008 - imx219 at 19.2 MHz

Lets imx219 accept a 19.2 MHz clock and dump a sensor's ID header and EEPROM. It is how
both sensors were identified, before they moved to the CCS driver.

## 9009 and 9010 - buffers without an IOMMU

Without an IOMMU the VFE only gets the first segment of a scatter-gather buffer and
writes the whole frame from there. `9009` refuses such buffers; `9010` switches CAMSS
to contiguous CMA buffers when there is no IOMMU, which is what makes full-size frames
work.

## 9012 - CSID and VFE clocks for msm8974

camss sizes the VFE clock for raw dumps as if it moved 64 bits a cycle, and the CSID
clock from the link frequency alone. On msm8974 both were too low for a four-lane
RAW10 stream. This raises them while a proper rule is worked out.

## 9013 - the stock IMX200 register tables

Writes the init table and mode-0 tables from the stock firmware's
`SOI20BS0_IMX200.dat` after power-on. The `imx200_stock` module parameter picks which
groups to write (1 init, 2 lane setting, 4 the rest of mode 0, 8 sizes, 16 clock
registers, 32 D-PHY timings). `9` is the combination that gives real frames.

