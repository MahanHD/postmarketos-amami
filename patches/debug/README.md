# Diagnostic patches

None of these belong in a build you actually use. Each one answered a question that
could not be answered from the outside, and keeping them means the next question of
the same shape costs a module reload instead of a kernel build.

To use one, add it to the `source=` list in the kernel APKBUILD after the numbered
patches. They are numbered from 9000 so they always apply last and never renumber
the real series. Take it out again before the build is used for anything else.

Patches whose code path is gone (the CCS camera driver, the first contiguous buffer
attempts, now `0115`) were removed in the 2026-10-16 cleanup; git history has them.

## 9000 - allow writing registers through regmap debugfs

Turns the `#undef REGMAP_ALLOW_WRITE_DEBUGFS` in
`drivers/base/regmap/regmap-debugfs.c` into a `#define`, which makes every regmap
register writable from `/sys/kernel/debug/regmap/*/registers`.

This is how register experiments go without a rebuild each: the WLED sink settings
were poked live this way while the backlight stride bug (`0013`) was being found.

It is a large hole in a running system: anything with a regmap becomes writable by
root, including PMIC rails. Only build it when you are actively poking at registers,
and expect to be able to switch the device off by writing the wrong one.

## 9001 - serve an extra sensor registry group

Adds `extra_gid`, `extra_offset` and `extra_size` module parameters to
`qcom_sns_reg`, so one registry group can be mapped at load time:

    modprobe qcom_sns_reg extra_gid=2691 extra_offset=0x1700 extra_size=0x100

The offsets in that driver's `group_map` are observed rather than documented, and
Android's sensor daemon does not contain them, so the only way to find the one the
DSP wanted for the accelerometer was to try candidates. This turned each candidate
into a module reload instead of an eight minute kernel build. It found `0007`.

Bad registry data wedges the sensor manager past both a module reload and a
remoteproc restart, so a wrong guess costs a reboot.

## 9002 - trim the offloaded scan request

Adds `scan_ie_mode` to `wcn36xx`, which trims the variable length IE block off the
end of `START_SCAN_OFFLOAD`:

    0 - send the IEs as usual          (593 bytes here)
    1 - no IEs, keep the ie_len field  (471 bytes)
    2 - no IEs and no ie_len field     (469 bytes)

Written to test whether the firmware was rejecting the request on length. It was
not: all three were ignored identically, which ruled out a whole family of guesses
in one build. The answer was a capability bit, `0010`, found in Qualcomm's prima and
the upstream patch history. Kept because "does the firmware care about the length of
this message" is a question that will come up again.

## 9003-9005 - GPU, IOMMU and suspend probes

`9003` logs each a3xx GPU init step, `9004` dumps the SMMU context bank state, and
`9005` dumps the MPM's vMPM enable masks at suspend. They go with the parked work in
`../parked/`: `0105` (GPU power-on fixup), `0037`/`0038` (display IOMMU) and the
suspend ops.

## 9007 - describe the front camera

Adds the front IMX132 to amami's device tree as `nokia,smia`, with its MCLK, rails
and reset line. It stays unlinked from CAMSS until the sensor has a driver, because
CAMSS waits for every linked sensor before registering anything.

## 9022 - write IMX200 registers just before stream-on

Adds an `imx200` module parameter, `dbg_regs`, a list of `0xAAAAVV` values (16-bit
address, 8-bit value) written after the mode tables and before the controls:

    echo 0x300400,0x30057f > /sys/module/imx200/parameters/dbg_regs

This is how 0x3004-0x3005 was pinned down (review pass 2). It was written against
the driver order of r223 (mode before stream-on), so it needs rebasing onto the
current `0103` before it goes back into a build.
