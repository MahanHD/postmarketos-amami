# Port review

A review of everything in this repository, done in passes small enough to finish in one
session each, so nothing depends on one long run. Each pass reads its area in full,
compares it with stock where that applies, fixes what it finds and records it here.

| Pass | Area | State |
|---|---|---|
| 1 | GPU and GPU memory (`0089`, `0105`-`0114`, `debug/9021`) | done, r220 |
| 2 | Camera stack: imx200 driver, camss patches, `recipe/libcamera`, `recipe/libdng`, `recipe/libmegapixels`, `recipe/megapixels`, `userspace/megapixels` | to do |
| 3 | amami and msm8974 device tree: CPU rail and OPPs, regulators, the DT patches | to do |
| 4 | The other kernel patches, by subsystem: display, sensors, charging, CPU hotplug, WiFi/BT, audio | to do |
| 5 | Tools, recipes and docs: stale or contradicting text, tools nobody uses | to do |

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
