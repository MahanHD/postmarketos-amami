# Next steps

Written 2026-09-12, after the session that added CPU thermal throttling, fixed the
core-wedging bug in our own cpufreq patches, and produced the first power numbers.

Ordered by what is worth doing next, not by how hard it is.

## What we can measure now

Worth knowing before picking anything up, because these did not exist yesterday and
they change what is cheap:

- **An ammeter.** `0023` fixed `qcom-spmi-iadc`, so
  `/sys/bus/iio/devices/iio:device0/in_current1_raw` reports real battery current in
  microamps, signed, at about 0.55 mA resolution. Two independent sense resistors
  agree within 5-7%, which is why the numbers are trustworthy. Anything that claims
  to save power can now be A/B'd in minutes instead of argued about.
- **pstore.** `ramoops@3e8e0000` is live with a 1 MB console buffer. A panic or a
  soft reboot leaves the log in `/var/lib/systemd/pstore/` (systemd-pstore *moves* it
  out of `/sys/fs/pstore`). It does not survive a forced power-off - photograph the
  screen for a hard hang.
- **A panic net.** The standard command line carries
  `sysctl.kernel.panic_on_rcu_stall=1 panic=10 rcupdate.rcu_exp_cpu_stall_timeout=21000`,
  so a wedged core reboots itself with a record rather than needing the battery
  pulled. Keep all three together - see the README for why the third is not optional.
- **A test pattern that works.** Flash a known-good kernel, `fastboot boot` the
  experiment so the flashed one stays as the fallback, change one variable, soak past
  the known failure point. That is what found the cpufreq bug.

## 1. GPU IOMMU

The biggest single win left: `msm.vram=192m` costs 192 MB on a 2 GB phone.

`0017`, `0018` and `0019` are written and in `patches/` but out of the build.
`0017` makes `qcom,iommu-secure-id` optional, which is required because downstream's
`kgsl_iommu` has none; `0018` adds the node; `0019` adds the `alt` clock.

Start by putting `0018` back in the build **with** `0019`, because the first attempt
hung the boot with only the OXILICX interface and bus clocks and the GFX3D clock is
the obvious suspect. Use `fastboot boot`, not a flash. If it hangs, pstore now
answers why instead of leaving us blind as it did the first time.

Expect this to be open-ended. Upstream has not solved it either: Matti Lehtimaki's
`qcom-msm8974-5.19.y-iommu` branch is, in Luca Weiss's words, "a semi-working branch
but hitting random issues with it". One thing worth keeping from reading it - the
`#if 0` block of register pokes there is not guesswork, it is downstream's
`qcom,iommu-bfb-regs`/`-data` pair for `kgsl_iommu` verbatim, and that is the
non-secure init the GPU IOMMU needs.

**Done when:** the GPU renders with `iommus` bound and `msm.vram` dropped from the
command line, and `free` shows the 192 MB back.

## 2. Where 252 mA of idle draw goes

Idle with the screen off measures 252 mA. That is high for an idle phone and the
number is suspicious rather than explanatory - something is probably busy that need
not be. Worth an hour with the ammeter before any bigger power work, because it may
be one runaway wakeup rather than anything structural.

Places to look: `/proc/interrupts` deltas over a quiet minute, `/sys/kernel/debug/wakeup_sources`,
the DSP and WCNSS remoteprocs, and whether the GPU is actually reaching its lowest
devfreq state when nothing is drawing.

**Done when:** either the draw is explained and reduced, or we can say what each
major consumer costs.

## 3. A suspend number, and deep suspend

Everything measured so far is *awake*. There is no s2idle standby figure at all, and
standby is what decides whether the phone survives a night on the shelf.

Measuring it needs care: the logger cannot sample while suspended, so take voltage
and capacity either side of a timed `rtcwake`, over long enough that OCV noise does
not swamp the delta. Bear in mind `capacity` is OCV-derived and recovers after load,
so it is not a fuel gauge.

Then the real question: the port only does `s2idle`, never deep suspend. That likely
touches the same SPM machinery as the core-wedging bug, so doing it after #2 means
arriving with better instincts about this hardware.

**Done when:** we know the standby drain in mA, and whether deep suspend is
reachable.

## 4. Raise the 960 MHz cap

The CPU runs at 960 MHz of an available 2150.4 MHz. The full PVS table is recovered
and recorded in the README; the blocker is that nothing in mainline drives VDD_APC,
and the rail cannot even be read - PM8841 returns zeroes over SPMI.

Now partly easier: with per-CPU cpufreq policies and a working ammeter we could at
least characterise what higher OPPs cost thermally and electrically before deciding.
But without rail control, raising the ceiling is an under-volted overclock. Do not
ship one.

**Done when:** either the rail is controllable, or we have written down clearly why
960 MHz stands.

## 5. Audio

Unchanged and still the largest untouched area: no APR/SLIMbus device tree and no
WCD9320 codec driver. A project, not a task. The DSP boots and every sensor on it
works, so the groundwork is not nothing.

## Smaller loose ends

- **The CPU wedge is fixed but only partly explained.** `0022` removes the cause, but
  the two observed failures had different signatures - one printed RCU stalls for 26
  minutes with two cores alive, the other printed nothing at all. There may be a
  second bug hiding behind the first.
- **`reboot bootloader` is a dead end.** The `reboot-mode` node exists and
  `syscon-reboot-mode` binds, but Sony's S1Boot ignores the Qualcomm magics at offset
  `0x65c`. Getting to fastboot still means holding Volume Up while plugging in. Do not
  spend more time here without S1Boot internals.
- **`BAT_THERM` sits close to the limit.** 642 mV needed the extended jeita band to be
  accepted. It works, but it is not understood *why* a normal reading lands that near
  the edge - a wrong assumption about the reference or the thermistor curve would be
  worth knowing before trusting the charger in the cold.
- **Charging is supply-sensitive.** A PC USB port cannot both run this phone and
  charge it. Always test charging on a real supply.
