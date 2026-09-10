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
