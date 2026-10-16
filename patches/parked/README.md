# Parked patches

Out of the build, each with a known way back. Everything else that left the build
was deleted in the 2026-10-16 cleanup because something replaced it or a test showed
it changed nothing; git history has those.

## 0037, 0038 - the display controller behind its IOMMU

`0037` adds the MDP's SMMU and points the display at it, which would free the 192 MB
VRAM carveout. The panel goes black: the SMMU's table walker faults reading the page
tables, while the GPU's identical SMMU walks the same memory. `0038` writes stock's
BFB register table from the reset hook; it reads back right and changes nothing.
The open question and what was ruled out are in `docs/notes.md` (GPU IOMMU). Check
the panel by looking, not by `fb0` or `glxinfo`, after touching this.

## 0077, 0082, 0083, 0084 - deep suspend

The suspend ops and the CPU and SoC collapse at system suspend. Deep suspend measured
no better than s2idle (cpuidle already collapses the CPUs, and L2 off never wakes), so
they are out. `0077` is not inert if re-added: registering suspend ops makes `deep`
the default `mem_sleep`. `0082` on its own does not wake. Measurements are in
`docs/notes.md` and `docs/measurements/`.

## 0091, 0092, 0093, 0095, 0096 - the generic CCS sensor driver

Fixes to mainline's CCS driver for Sony's SMIA sensors: junk in CCS-only limit
registers, sub-device state broken by the 6.16 conversion (two patches), the sensor
being started twice, and the helper every quirk register table goes through. The
IMX200 left CCS for its own driver (`0103`); these wait for the front IMX132, which
`../debug/9007` describes as a `nokia,smia` CCS sensor. The IMX200-only CCS patches
(its quirk and stock tables) were deleted.

## 0105 - the a3xx power-on fixup after every power-on

kgsl's fixup, run the way kgsl runs it; its 491 dwords match the stock kernel's
buffer. An hour-long soak gave 10 hangs and 17 hw_init idle timeouts against none
without it. The GPU hangs it was for were later traced to the shrinker (`0113`) and a
missing soft reset (`0111`). Lead if it is ever needed: it leaves a330v2's
`RBBM_CLOCK_CTL` bits 17:16 at the a330v1 value.
