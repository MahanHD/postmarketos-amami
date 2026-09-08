#!/usr/bin/env python3
"""Emit the C init functions for all four amami panel variants."""
import re
WS = "/home/mahan/Devices/Xperia-Z1-Compact/postmarketOS"
src = open(WS + "/dts/dsi-panel-amami.dtsi").read()

DCS_SHORT = {0x05, 0x15}
DCS_LONG = 0x39

def convert(b, indent="\t"):
    out, i = [], 0
    while i < len(b):
        if i + 7 > len(b):
            break
        dtype, wait = b[i], b[i + 4]
        dlen = (b[i + 5] << 8) | b[i + 6]
        pl = b[i + 7:i + 7 + dlen]
        i += 7 + dlen
        if not pl:
            continue
        args = ", ".join(f"0x{x:02x}" for x in pl)
        if dtype in DCS_SHORT or dtype == DCS_LONG:
            out.append(f"{indent}mipi_dsi_dcs_write_seq_multi(dsi_ctx, {args});")
        else:
            out.append(f"{indent}/* dtype 0x{dtype:02x}: {args} */")
        if wait:
            out.append(f"{indent}mipi_dsi_msleep(dsi_ctx, {wait});")
    return out

def grab(node, prop):
    m = re.search(re.escape(prop) + r'\s*=\s*\[(.*?)\]', node, re.S)
    return None if not m else [int(x, 16) for x in m.group(1).split()]

# node label -> (C function suffix, human name)
VARIANTS = [
    ("somc,novatek_default_panel",        "default",  "default novatek 720p vid"),
    ("somc,novatek_jdi_720p_panel",       "jdi",      "jdi novatek 720p vid"),
    ("somc,novatek_auo_720p_panel",       "auo",      "auo novatek 720p vid"),
    ("somc,novatek_auo_720p_panel_new_id","auo_new",  "auo novatek 720p vid new id"),
]

starts = []
for label, suffix, name in VARIANTS:
    idx = src.index(label)
    starts.append((idx, label, suffix, name))
starts.sort()

chunks = []
for n, (idx, label, suffix, name) in enumerate(starts):
    end = starts[n + 1][0] if n + 1 < len(starts) else len(src)
    chunks.append((suffix, name, src[idx:end]))

out = []
for suffix, name, node in chunks:
    early = grab(node, "somc,mdss-dsi-early-init-command") or []
    init = grab(node, "somc,mdss-dsi-init-command") or []
    out.append(f"/* {name} */")
    out.append(f"static void amami_init_{suffix}(struct mipi_dsi_multi_context *dsi_ctx)")
    out.append("{")
    out += convert(early)
    out.append("")
    out += convert(init)
    out.append("}")
    out.append("")
    print(f"// {suffix}: early={len(early)}B init={len(init)}B", flush=True)

open(WS + "/dts/amami-variants.c", "w").write("\n".join(out))
