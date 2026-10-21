#!/usr/bin/env python3
"""Emit the C init functions for all four amami panel variants.

  gen_all_variants.py dsi-panel-amami.dtsi amami-variants.c
"""
import sys

from convert_cmds import convert, grab

# node label -> (C function suffix, human name)
VARIANTS = [
    ("somc,novatek_default_panel",        "default",  "default novatek 720p vid"),
    ("somc,novatek_jdi_720p_panel",       "jdi",      "jdi novatek 720p vid"),
    ("somc,novatek_auo_720p_panel",       "auo",      "auo novatek 720p vid"),
    ("somc,novatek_auo_720p_panel_new_id","auo_new",  "auo novatek 720p vid new id"),
]

src = open(sys.argv[1]).read()

# each variant's node runs to the next one's label
starts = sorted((src.index(label), suffix, name) for label, suffix, name in VARIANTS)
out = []
for n, (idx, suffix, name) in enumerate(starts):
    end = starts[n + 1][0] if n + 1 < len(starts) else len(src)
    node = src[idx:end]
    early = grab(node, "somc,mdss-dsi-early-init-command") or []
    init = grab(node, "somc,mdss-dsi-init-command") or []
    out.append(f"/* {name} */")
    out.append(f"static void amami_init_{suffix}(struct mipi_dsi_multi_context *dsi_ctx)")
    out.append("{")
    out += convert(early, ctx="dsi_ctx")[0]
    out.append("")
    out += convert(init, ctx="dsi_ctx")[0]
    out.append("}")
    out.append("")
    print(f"// {suffix}: early={len(early)}B init={len(init)}B", flush=True)

open(sys.argv[2], "w").write("\n".join(out))
