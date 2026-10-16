# Port review

A review of everything in this repository, done in passes small enough to finish in one
session each, so nothing depends on one long run. Each pass reads its area in full,
compares it with stock where that applies, fixes what it finds and records it here.

| Pass | Area | State |
|---|---|---|
| 1 | GPU and GPU memory (`0089`, `0105`-`0114`, `debug/9021`) | done, r220 |
| 2 | Camera stack: imx200 driver, camss patches, `recipe/libcamera`, `recipe/libdng`, `recipe/libmegapixels`, `recipe/megapixels`, `userspace/megapixels` | done, r226 |
| 3 | amami and msm8974 device tree: CPU rail and OPPs, regulators, the DT patches | done, r235 |
| 4 | The other kernel patches, by subsystem: display, sensors, charging, CPU hotplug, WiFi/BT, audio | done but audio (parked), r239 |
| 5 | Tools, recipes and docs: stale or contradicting text, tools nobody uses | patches and docs cleaned 2026-10-16 (worklog, "Cleanup"); tools to do |

## Pass 1: GPU and GPU memory

Read: `0089`, `0106`-`0113` in full, `0105` (parked) and `debug/9021`, against the
6.16.12 sources they apply to (`msm_gem.c`, `msm_gem.h`, `a3xx_gpu.c`, `gdsc.c`,
`mmcc-msm8974.c`, `arm-smmu-qcom.c`, `msm_gpu.c`, `msm_gpu_devfreq.c`).

Fixed:

- `0113` said "carveout object" as `!obj->filp`, a third definition next to
  `use_pages()` (`!vram_node`, used by `0106`) and true for imported dma-bufs too. It now
  tests `vram_node`, which is set when a carveout object is made and never cleared.
- `0089` had no header, and its comment still said carveout objects are what you get
  "when the GPU runs without an IOMMU"; since `0034` it is the display that has none.
  The `!obj->filp` test stays: it is the exact condition for the dereference it guards.
- `0108` hand-encoded the `CP_SET_CONSTANT` address as
  `0x00040000 | (REG - 0x2000)`. It now defines kgsl's `CP_REG()` (upstream's disabled
  code used a `CP_REG()` that no longer exists) and names the register.
- `debug/9021` (the `retain_mem` switch) is out of the build: it was for testing whether
  memory retention kept the GPU from recovering, and the cause turned out to be the
  shrinker (`0113`). The file stays in `patches/debug/`.
- `tools/gpu-hang-inject.py` takes `CANARY_TIMEOUT`, which until now only the phone's
  copy had.

Checked and left as they are:

- `0106` clears carveout pages through the cached alias and writes them back before the
  GPU or display can see them; the sync calls cover both WC and cached buffers.
- `0107` decodes the error interrupts as kgsl's `a3xx_err_callback()` does, ratelimited,
  and leaves recovery to hangcheck.
- `0109` is minimal and matches stock's `qcom,retain-mem`/`retain-periph`.
- `0110`: the BFB offsets from the device tree are written without a bounds check, and the
  table is re-read from the device tree on every resume. The tree is trusted and it is
  twelve values, so neither is worth code.
- `0111`: `df->lock` is never taken together with `gpu->lock`, so the lock in
  `a3xx_pm_suspend()` cannot deadlock against recovery; the reset only runs with the
  clocks on, and system suspend skips it when the GPU is already suspended.
- `0113` also closes a second problem: a carveout object's `iova` is set once from its
  physical address, so one evicted and re-pinned elsewhere would have kept a stale
  `iova`. With nothing evicted that cannot happen.

Verified on r219: two debugfs shrinks and six minutes with no Xorg hang, three injected
hangs all recovered with canaries before and after, no warnings.

### `/code-review` of pass 1 (medium, the eight built GPU patches)

Ten candidates, each checked against the source:

| # | Finding | Verdict | Done |
|---|---|---|---|
| 1 | `retire_submit()` divides with `do_div()`, which takes only the low 32 bits of the 64-bit `elapsed`, so `if (elapsed)` does not stop a division by zero | real, upstream | new `0114`: `div64_u64()` |
| 2 | a purge's `put_iova_vmas()` frees the vma `vram_node` points into and leaves it dangling | real, latent (only tested, never dereferenced) | `0089` clears it |
| 3 | recovery replays through `funcs->submit()`, which does not update `cur_ctx_seqno`, so every replayed submit runs its context restore | real, and right: the GPU was just reset, so its context state is gone | none |
| 4 | `0111` reset before `msm_gpu_pm_suspend()`; if suspend then failed, the core stayed reset with `needs_hw_init` false | real | `0111` reworked |
| 5 | `0111` missed a core the bootloader left powered, which kgsl's check covers | real | `0111` now resets at the start of every hw_init, kgsl's placement, and takes devfreq's baseline again under its lock; recovery goes through it too |
| 6 | `0110` read the device tree on every resume, ignored its own error and wrote offsets unchecked | real, minor | `0110` reads and checks the table once in `cfg_probe` |
| 7 | `0107` decoded four interrupts `A3XX_INT0_MASK` leaves off | real (kgsl's mask is the same) | branches dropped |
| 8 | `0110` put Sony's BFB values in the shared msm8974 dtsi | real: LineageOS's table differs | moved to amami's dts |
| 9 | clearing `cur_ctx_seqno` belongs in shared `adreno_hw_init()`, not per generation | valid | for upstreaming; only a3xx can be tested here |
| 10 | `0106` clears and syncs every carveout allocation | true, but clearing on free would cost the same | none |

Verified on r220: the twelve BFB registers read back stock's values after a resume
(honami's dtb has none); ten soak cycles with the SMMU pinned, so every resume skipped the
power collapse: 0 hangs, no warnings, 190 s suspended; five injected hangs recovered, and
two debugfs shrinks were followed by five minutes without a hang.

Found for later passes:

- 97 of the 107 patches (83 of those built) have no From/Subject header; their reasons
  live in `README.md` and the docs. Needed before anything goes upstream (pass 4).
- `0087` (amami camss) applies with fuzz 2 at a 338 line offset in every build (pass 3).

## Pass 2: camera stack

`/code-review` (medium) over `0085`-`0087`, `0090`-`0104`, `recipe/libcamera`,
`recipe/libdng`, `recipe/libmegapixels`, `recipe/megapixels`, `userspace/` and
`tools/camera/`. Ten candidates:

| # | Finding | Verdict | Done |
|---|---|---|---|
| 1 | `imx200` starts streaming before it writes the mode, so the first frame or two of a binned stream arrive at full size into buffers sized for the mode | real, and worse than it looked: the VFE wrote them past the buffer | new `0116`; see below |
| 2 | the mode tables reset the digital gain after the controls were applied | real; worse again, stream-on reset exposure, gain and frame length too | `0103`: controls after the mode, after stream-on |
| 3 | autofocus kept the lens powered by resending its position every 20 frames, longer than the lens's 3 s power-down at night frame rates | real | `0103` links the lens to the sensor (runtime PM device link); `recipe/libcamera` `0007` drops the resend |
| 4 | autofocus credits a sharpness sample to the position just requested, while frames in flight were exposed at the old one | plausible, not shown | none yet; AF converges in practice |
| 5 | `reference_ == 0` means "not set", so an all-black scene never sets one | real, harmless (no rescan in the dark) | none |
| 6 | the shipped kernel carries debug patches: `9006`, `9009`, `9010` (the camera depends on them), `9007`, `9008` | real | `9006`/`9009`/`9010` became `0115`; `9007`/`9008` out of the build |
| 7 | a failure after stream-on left the sensor streaming | real | `0103` puts it back to standby |
| 8 | the IMX200 parts of the CCS patches are dead since `0104` | real | `0091`-`0096` and `0098` out of the build (kept for the IMX132) |
| 9 | the AF range in `imx200.yaml` is this unit's EEPROM values | valid | none: there is no interface to pass the EEPROM's range to libcamera |
| 10 | `settle-sweep.py` counted interrupts on two CPUs of four | real | counts every online CPU |

### Stream-on and 0x3004-0x3005

The finding behind #1 was that stream-on resets the readout registers. Stock writes
0x3004-0x3005 first in every mode table, and with it set the registers survive
stream-on (read back over `i2c-3` with the sensor powered by hand). But 0x3004-0x3005
selects one of the sensor's own clock presets: every value except the reset 0x007f gave
frames of pure noise or none (`debug/9022` tried each), with or without stock's 0x0108
lane count, because the presets are made for stock's 8 MHz clock and this port runs the
sensor from 19.2 MHz through the SMIA PLL registers. 0x007f means "no preset", and with
it every stream-on reloads the readout defaults. So the mode has to be written after
stream-on, as before, and the oversized first frames have to be contained where they
land.

### The VFE wrote past its buffers

camss runs RDI write masters frame-based, and in that mode the image size and buffer
configuration registers are ignored: an oversized frame is stored from the buffer
address on, however long it is. Measured with a canary (`tools/camera/canary.c`: four
buffers, two of them never queued and filled with 0xa5): a full-size frame into a
2624x1976 stream overwrote 5.8 MB of a buffer that was never queued, and stock's
`WR_BUFFER_CFG` on its own did not stop it. In line-based mode with the image size set,
the canary survived and correctly sized frames came out identical. `0116` writes the
VFE 4.1 RDI masters line-based and aligns RDI `bytesperline` to 16 bytes, as the PIX path
already is. On r226 the canaries stay intact in every mode.

### The 1312x988 mode never worked

The stock 4x4 modes (1312x988) depend on the output width taking effect at stream-on.
Written after it, binning switches but the sensor keeps sending 2624-pixel lines: the
raw data has a period of 3280 bytes, the VFE completes one frame in four, and the
stream after it wedges camss. Every 1312 frame since the mode-after-stream-on change was
garbage, r220 included (the SMIA scaler cannot be switched on mid-stream either). The
mode is gone from `0103`, and Megapixels previews at 2624x1976.

Verified on r226: canaries intact in all three modes; every mode streams with the
registers, the 2x digital gain and the lens state as set, and the lens powers down with
the sensor afterwards; Megapixels previews at 2624x1976 and libcamera r8 streams 720p at
33 fps. The colour check of a daylight photo is still to do.

### Follow-up: Megapixels crashed taking photos (r227)

Removing 1312x988 broke Megapixels. It picks its preview mode by a score with an integer
division and a best score starting at 0, so no mode more than twice the preview's area
can win; with 2624x1976 the smallest mode, it fell back to previewing at 5248x3936. Its
textures took 156MB of the 192MB carveout, and a photo aborted on
`glCheckFramebufferStatus()` after `GL_OUT_OF_MEMORY`. The slow night auto exposure noted
above was this full-resolution preview. `recipe/megapixels` r7 scores in floating point
from -INFINITY and the preview runs at 2624x1976, holding 53MB.

Photos then failed one time in two, on the switch back to preview: the capture peaks at
185MB, and the carveout ran out while it held 23MB of Mesa's cached buffers marked
`MSM_MADV_DONTNEED`, which only the shrinker purges, on system memory pressure. `0117`
purges them from the allocation that does not fit. Verified on r227: four photos in a
row, no `get_pages` failures, every DNG and JPEG written.

The same evening Megapixels' bursts filled the 939 MB RAM-backed /tmp (up to 11 frames of
26 MB a photo, of which `postprocess.sh` reads one) and photos developed in parallel; the
Xfce session aborted on a libwnck icon assertion in the middle of that. Megapixels r8
captures two frames and queues the development, LightDM logs back in after a session
ends, and the carveout is 256 MB, since 192 MB still ran out on photos taken in a row.
The shifted preview was the start-up frames: on the fade test pattern (`rowwatch`,
15,000 frames) every stream had bad frames up to the third, fourth or fifth and none
after, and Megapixels, starved of GPU memory, kept showing one. `0103` reports 5 through
`g_skip_frames` (r228), and camss drops them in hardware; every frame delivered is now
aligned, and Megapixels' preview on the test pattern is unchanged across three photos.
The 96-row shift seen earlier in two long raw runs was not reproduced on the test
pattern and was most likely the scene moving under the profile comparison.

### Follow-up: a crash, dark and purple photos (r229-r232, Megapixels r9-r13)

The next morning's first photo crashed Megapixels. The camera got one full-size buffer
(`vmalloc_node_range for size 25825280 failed`): CMA is in highmem, and each buffer was
remapped into the 240 MB vmalloc area. Megapixels exited on the failed `DQBUF`, and its
GL thread segfaulted in Mesa during the exit. `0115` now allocates the camera buffers
without a kernel mapping (r229), which on 32-bit ARM had dma-direct return them unzeroed
and uncleaned from the cache; `0118` (r230) hands them to ARM's own allocator, and
buffers just reused after streaming read back all zero. With the preview running, the
kernel maps 0.45 MB of camera buffers instead of 57 MB.

A second photo taken soon after the first came out dark twice: once at 1% of the
brightness (both frames at the default exposure), once 12x dark (the exposure applied,
the gain not yet). Five skipped frames did not cover the writes after stream-on: on 16
long-exposure streams the sixth and seventh frames still had the default exposure. Eight
are skipped since r231, and since r232 the shading table goes out in one bulk write, which
ends the window at about 120 ms, loaded or not. Four photos 15 s apart then gave eight
burst frames within 17% of each other, all at full exposure.

Development took 2.5 to 3 minutes a photo with the preview open, against 95 s on an idle
phone. ImageMagick's `-sharpen` and `-sigmoidal-contrast` are now an unsharp mask and a
lookup table (Megapixels r9, 59 s to 35 s, 62 dB PSNR against the old JPEG), and the code
scanner, which held a core for as long as the camera was open, rests a second between
scans at density 2 (r12, 92% to 38%).

A photo then came out purple with the preview right: the first auto white balance step
after a photo sent both gains to the 4.0 limit, and the DNG could be written then.
`photo-keeps-white-balance.patch` had kept the gains across the mode change but not
given them back to the debayer, which resets them, and the step itself ignored the colour
matrix and gamma, so it overshot. Megapixels r13 fixes both; the step now lands on the
scene's gains in one move, and the next photo's neutral matched its raw data to 0.002.

## Pass 3: device tree

`/code-review` (medium) over the 27 patches that touch the device tree, against the
bindings and Sony's stock tree. Ten candidates, each checked against the source, stock
(`14.4.A` kernel-copyleft and the `14.6.A` dtbs) and the phone:

| # | Finding | Verdict | Done |
|---|---|---|---|
| 1 | `0024`: the extended BTC window, with no derating, lets the battery charge at full current far into the hot band; stock derates above 45C | real, and the reason for the window was wrong | new `0119`, `0024` rewritten, `0069` gets the battery table; below |
| 2 | `0004`: `charge-full-design` 3140 mAh, honami's pack | real: Sony's profile for amami (`bms-batterydata-ray.c`) is 2420 mAh; the OCV table was already from it | `0004` |
| 3 | `0112`: voltages for one bin only, so every other unit loses its whole OPP table | real | every stock bin, plus a worst-case fallback |
| 4 | `0001`: amami's touchscreen fixes are in the shared rhine dtsi, changing honami | half: honami's stock tree uses the same S3 rail and 200 ms, so those stay shared; the X inversion is amami's | `0001` keeps it, new `0120` drops it for amami |
| 5 | `0035`: a debug probe writes `0xdeadbee0` into the SMMU on every boot, into global space once the banks move | real | removed; the comment keeps the measurement |
| 6 | `0110`: the GPU SMMU's BFB table only in amami's dts | valid by design: LineageOS has a different table for the same SoC | none |
| 7 | `0073`-`0075` route PMIC and tsens interrupts through the MPM in the shared dtsi, needing `QCOM_MPM` | real for other boards (`=y` here) | none until upstreaming |
| 8 | `0015`/`0034`: unvolted OPPs and the GPU SMMU in the shared dtsi apply to every msm8974 board | real for other boards | none until upstreaming |
| 9 | `0050`: the codec MCLK pin has no pinctrl state | real, known, audio is parked | none |
| 10 | properties and compatibles without bindings (smbb, smmu, camss, imx200, bu64296, panel) | real, an upstreaming blocker | the new smbb properties are in the binding |

### The battery window

The SMBB's BTC comparator stops charging outside a window, each edge a fraction of the
thermistor's reference (hot 35% or 25%, cold 70% or 80%), and charges at full current
inside it. On the battery thermistor table those edges are about 40C, 57C, 4C and -7C.
`0024` had set `qcom,jeita-extended-temp-range` because the thermistor "at room
temperature" read 34%, which the narrow window counts as hot. But 34% is 42C on the
battery table: the battery was warm, not misread. The extended range moved both edges
and nothing derated, so the pack charged at 1.3 A to 4.35 V from -7C to 57C. Stock
(`qpnp-charger`, Sony's amami node) leaves the edges to the hardware and derates in
software: 650 mA to 4.2 V above 45C, 650 mA below 10C, 2C of hysteresis.

`0119` adds that derating to `qcom_smbb`, polled every 30 s while a charger is
connected, and lets each window edge be chosen on its own. `0024` takes the extended
hot edge (the narrow one stops a warm-day battery from charging at all), the narrow
cold edge (no charging below freezing) and stock's derating. `0069` replaces the
generic 100k curve, which read 40.7C where the battery table reads 43.3C, with the
downstream table.

On r234, `0x1249` reads `0x80` (hot 25%, cold 70%). Four loaded cores took the battery
from 43.7C to 45.3C in about three minutes; the driver logged "warm charging" and
`current_max`, `voltage_max` and the recharge threshold went from 1.3 A, 4.35 V and
4.20 V to 650 mA, 4.2 V and 4.04 V. Through 25 minutes of cooling from 46.9C to 44.1C
it stayed warm, as the hysteresis says. The way back to normal (below 43C) was not
seen: this room keeps the idle battery near 43.7C. r235 rounds the recharge threshold
to its 20 mV grid itself (r234 logged the rounding) and stays quiet about the ADC
for the first polls after boot, when it has not probed yet.

## Pass 4: the other kernel patches

Two `/code-review` (medium) runs: 4A over the panel, charger and battery, sensor,
WiFi, backlight and MDP patches plus `0119`; 4B over the SoC core (HFPLL data, CPU
hotplug, SPM and MPM, the GPU's arm-smmu patches pass 1 did not read, OCMEM). The
audio patches (`0049`-`0067`, over 10,000 lines) are parked work and were left out.
Eighteen candidates:

| # | Finding | Verdict | Done |
|---|---|---|---|
| A1 | `0119`: the derating work can outlive a failed probe | real | device-managed work |
| A2 | `0119`: `pm_stay_awake()` does not stop a plain write to `/sys/power/state` | real, and the patch claimed it did | derate while unwatched (suspend, before the first reading) instead of a wakeup source |
| A3 | `0119`: derating configured without a `batt-therm` channel silently never applies | real | the channel is required, and the zone starts unknown (derated) |
| A4 | `0119`: the recharge threshold came from the unclamped request | real | userspace limits capped at the safe values first |
| A5 | `0069`: the battery thermistor read in absolute mode, the table is ratiometric | real; stock: `calibration-type = "ratiometric"` | `qcom,ratiometric` in `0071`; driver and hand calculation now agree to 0.01C |
| A6 | `0119`: two charger interrupts can race start against stop | real | the IRQs only kick the work, which checks for a charger itself |
| A7 | `0003`: one failed panel ID read fixes the fallback init until reboot | real | only a real read is kept |
| A8 | `0003`: a failed prepare leaves the enable GPIO high | real | dropped on that path |
| A9 | `0048`: the light device's sampling rate writes proximity's; its pointer is published before registration | real | both fixed |
| A10 | `0006` is unreachable since `0010` | real | `0006` dropped |
| B1 | `0080`: the parked flag plus 100 us is not proof the core is off; a live core can be reset | real | wait on the ACC power status (stock's `cpu-sleep-status`, bit 19), checked on the phone: 1 offline, 0 running |
| B2 | `0081`: a failed release loses the core for good | real | handshake restored on failure |
| B3 | `0079`: the warm boot address came from cpuidle | real | registered by hotplug itself |
| B4 | `0079`: the SPM lookup ran on the dying core and leaked a reference | real | looked up in a CPU hotplug teardown callback on the outgoing core |
| B5 | `0081`: `smp_wmb()` before MMIO | real | `wmb()` |
| B6 | `0080` changed re-online for other qcom SoCs | real | the handshake only for cores that went down by collapse |
| B7 | `0036` aligns to 64K/1M everywhere | valid by design here (the GPU maps the carveout through its SMMU) | upstreaming list |
| B8 | `0035` writes S2CR MemAttr without MTCFG, which the SMMU ignores | real, dead config, as downstream | dropped; S2CR 0xca001 to 0xc0001, GPU unchanged |

B4 took two attempts. The first looked the SPM up at `late_initcall_sync` and found
nothing (the SPM and SCM drivers had not probed yet); r236's boot checks passed, and
only a 60-cycle hotplug stress run showed every core parking in WFI and never coming
back. r237 does the lookup at offline time: 180 offlines, all by collapse, 180
returns, no failures.

Testing r238 found one more, not from the review: on some boots there were no sensors
at all. `qcom_smgr` probe gave up when the DSP refused the accelerometer (0x701) or
timed out, and only a lucky re-probe recovered it. A retry loop inside probe (r238)
made it worse, three boots of four without sensors: the DSP's registry requests
arrived the moment the loop gave up, so waiting in probe held them up. `0121`
enumerates from a work item instead. That exposed the real pattern: in 14 of 15
boots the sensors came up exactly when the ADSP had crashed ("Exception detected")
and restarted. The first ADSP run is bad on every boot: it faults, or it runs on
without bringing the sensors up. It is not the registry being late: a test patch
loading the registry driver before the DSP (r240) had it serving first in six boots
of six and changed nothing, so it was dropped. Open, in `next-steps.md`.

Three boots of 25 in the journal logged `oxili_gfx3d_clk status stuck at 'off'` and
then a disable of an already disabled clock, at the GPU's first power-up (4 s and
24 s); the GPU works afterwards. All three were on r239 or later and none of 11 boots
before, but the only change in r239 (`0121`) runs at about 30 s, after it, and 3 of
14 against 0 of 11 is not a difference yet. Open, in `next-steps.md`.

The audio patches remain unreviewed until audio resumes.

