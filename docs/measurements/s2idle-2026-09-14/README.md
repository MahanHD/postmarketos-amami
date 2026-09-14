# s2idle power, 2026-09-14

Raw data behind the suspend figure in `docs/next-steps.md` (Phase 2) and the
`xperia-z1c-battery-baseline` memory. Kernel **r56** (`uname -v` = `#57`), the
flashed known-good build - this measurement needs no IOMMU or audio work, so it
was taken on the installed kernel with no fastboot cycle.

Produced by `tools/s2idle-test.sh` with its defaults (2400 s phases, 180 s
settles). **The USB cable was out for the whole run**: on a host port the battery
floats, the external sense resistor sees only noise, and current does not respond
to load at all.

## The files

| file | what it is |
|---|---|
| `log` | phase markers and the four endpoint snapshots (`V0`, `V1`, `wake_immediate`, `V2`) |
| `awake.csv` | Phase A sampled every 20 s - `t,cap,uV,bl,i0,i1` |
| `settle.csv` | both settles sampled every 15 s - `tag,t,uV,i1,bl` |
| `susp_before`, `susp_after` | `/sys/power/suspend_stats/success`, 0 then 1 - the phone really did suspend once |

`i0` is the IADC's internal sense channel and `i1` the external 10 mOhm resistor
in the DT, both signed microamps (negative is discharge). They agree to 5-7%
across the run, which is what makes the numbers trustworthy - a single channel
would have been agreeing with nothing. `bl` is `bl_power`, and it reads **4** in
every sample, which is the check that the screen actually stayed off; a touch
wakes DPMS and would have silently turned a screen-off run into a screen-on one.

## Endpoints used

Every endpoint is read at the *same* load state - awake, screen off, after a
settle - because `capacity` and `voltage_now` here track **load**, not charge.

| point | t | uV | i1 |
|---|---|---|---|
| `V0` start of A | 1789375982 | 3954075 | -242200 |
| `V1` end of A / start of B | 1789378394 | 3878352 | -243900 |
| `V2'` end of B | 1789380968 | 3833034 | -244400 |

`V2'` is the **last row of `settle.csv`**, not the scripted `V2` snapshot. `V2`
landed on a -303858 uA spike and would have inflated the answer; the settle row
is matched to `V1`'s load within 0.2% (-243900 against -244400), which is the
whole point of sampling through the settle instead of trusting that 180 s was
enough.

## Result

Phase A: 75.7 mV of OCV drop over 2412 s at a measured 248 mA = **166.2 mAh**,
against 9.48% of pack on Sony's OCV curve - so full capacity is **~1750 mAh**
against 3140 nameplate, about **56% health**.

Phase B: 45.2 mV over the 2408 s suspend plus the 166 s of awake settle inside
the window, which back-converts to **156 mA suspended** against 248 mA awake
screen-off - only **37% saved**.

Conversion uses Sony's `qcom,pc-temp-ocv-lut` from `batterydata-rhine-amami.dtsi`
(25 C column), each reading first corrected for IR drop at its own measured
current. Do not shortcut it with a linear fit: the curve flattens toward lower
SoC (43 -> 36 -> 33 mV per 5%) and linear gives 132 mA instead of 156. The answer
is insensitive to the internal-resistance assumption - 100 mOhm and 150 mOhm give
156 and 160 mA.
