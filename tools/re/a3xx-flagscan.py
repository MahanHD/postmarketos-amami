"""Map the stock a3xx workaround flag bits to the code that tests them.

The flags live in a struct at [ctx+0x1868]: word 0 is the main set, word 1 a
second set. This follows registers linearly through each exported oxili_/rb_
function: wa = [ctx_reg+0x1860+8] (or via add #0x1860), w0 = [wa], w1 = [wa+4],
then reports the bit each test on w0/w1 looks at.
"""
import re, sys
import capstone
from elftools.elf.elffile import ELFFile

path = sys.argv[1]
e = ELFFile(open(path, "rb"))
data = open(path, "rb").read()
text = e.get_section_by_name(".text")
funcs = sorted((s['st_value'] & ~1, s.name, s['st_size'])
               for s in e.get_section_by_name(".dynsym").iter_symbols()
               if s['st_info']['type'] == 'STT_FUNC' and s['st_value'])
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
mem = re.compile(r"(\w+), \[(\w+)(?:, #(-?0x[0-9a-f]+|\d+))?\]$")
res = {}
for a, name, size in funcs:
    o = a - text['sh_addr'] + text['sh_offset']
    tag = {}  # reg -> 'base' | 'wa' | 'w0' | 'w1'
    for x in md.disasm(data[o:o + size], a):
        ops = x.op_str
        m = re.match(r"(\w+), (\w+), #0x1860$", ops)
        if x.mnemonic.startswith("add") and m:
            tag[m.group(1)] = "base"
            continue
        if x.mnemonic == "ldr" or x.mnemonic == "ldr.w":
            m = mem.match(ops)
            if m:
                d, b, off = m.group(1), m.group(2), int(m.group(3) or "0", 0)
                t = tag.get(b)
                if t == "base" and off == 8:
                    tag[d] = "wa"
                elif t == "wa" and off == 0:
                    tag[d] = "w0"
                elif t == "wa" and off == 4:
                    tag[d] = "w1"
                else:
                    tag.pop(d, None)
                continue
        regs = [r.strip() for r in ops.split(",")]
        src = [r for r in regs[1:] if r in tag and tag[r] in ("w0", "w1")]
        if x.mnemonic.startswith(("tst", "lsls", "ands", "and", "ubfx", "cmp")) and (src or (regs and tag.get(regs[0]) in ("w0", "w1") and x.mnemonic.startswith(("tst", "cmp")))):
            r = src[0] if src else regs[0]
            bits = None
            imm = re.search(r"#(0x[0-9a-f]+|\d+)", ops)
            if imm:
                v = int(imm.group(1), 0)
                if x.mnemonic.startswith("lsls"):
                    bits = [31 - v]
                elif x.mnemonic.startswith("ubfx"):
                    bits = [v]
                elif x.mnemonic.startswith("cmp"):
                    bits = ["cmp%x" % v]
                else:
                    bits = [i for i in range(32) if v >> i & 1]
            res.setdefault((tag[r], tuple(bits or ["?"])), set()).add("%s@%x" % (name, x.address))
        # writes clobber tags
        if regs and regs[0] in tag and not x.mnemonic.startswith(("tst", "cmp", "str", "b", "c")):
            tag.pop(regs[0], None)
for (w, bits), names in sorted(res.items(), key=lambda k: (k[0][0], str(k[0][1]))):
    print("%s bits %-14s %s" % (w, ",".join(map(str, bits)), " ".join(sorted(names))))
