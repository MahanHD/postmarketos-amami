#!/usr/bin/env python3
"""Convert Sony downstream mdss DSI command blobs into mipi_dsi_* C calls.

Blob format per command:
  dtype, last, vc, ack, wait, dlen_hi, dlen_lo, payload[dlen]
`wait` is a post-command delay in ms.
"""
import re, sys

DCS_SHORT = {0x05, 0x15}     # DCS short write, 0 / 1 param
DCS_LONG  = 0x39             # DCS long write
GEN_LONG  = 0x29

def grab(text, prop):
    m = re.search(re.escape(prop) + r'\s*=\s*\[(.*?)\]', text, re.S)
    return None if not m else [int(x, 16) for x in m.group(1).split()]

def convert(b):
    out, i, n = [], 0, 0
    while i < len(b):
        if i + 7 > len(b): break
        dtype, _last, _vc, _ack, wait = b[i], b[i+1], b[i+2], b[i+3], b[i+4]
        dlen = (b[i+5] << 8) | b[i+6]
        pl = b[i+7:i+7+dlen]
        i += 7 + dlen
        n += 1
        if not pl: continue
        args = ", ".join(f"0x{x:02x}" for x in pl)
        if dtype in DCS_SHORT or dtype == DCS_LONG:
            out.append(f"\tmipi_dsi_dcs_write_seq_multi(&dsi_ctx, {args});")
        elif dtype in (0x03, 0x13, 0x23, GEN_LONG):
            out.append(f"\tmipi_dsi_generic_write_seq_multi(&dsi_ctx, {args});")
        else:
            out.append(f"\t/* unhandled dtype 0x{dtype:02x}: {args} */")
        if wait:
            out.append(f"\tmipi_dsi_msleep(&dsi_ctx, {wait});")
    return out, n

src = open(sys.argv[1]).read()
# isolate the default novatek panel node only
start = src.index('somc,novatek_default_panel')
end   = src.index('qcom,mdss-dsi-panel-name = "jdi novatek 720p vid"')
node  = src[start:end]

for prop in ("somc,mdss-dsi-early-init-command",
             "somc,mdss-dsi-init-command",
             "qcom,mdss-dsi-on-command",
             "qcom,mdss-dsi-off-command"):
    b = grab(node, prop)
    if b is None:
        print(f"// {prop}: not found\n"); continue
    lines, cnt = convert(b)
    print(f"// ===== {prop}  ({cnt} commands, {len(b)} bytes) =====")
    print("\n".join(lines))
    print()
