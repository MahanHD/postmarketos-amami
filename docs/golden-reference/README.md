# Golden reference: WCD9320 on a working downstream stack

Captured 2026-09-18 from **LineageOS 18.1 (Android 11), kernel 3.4 downstream**,
on this exact phone, with audio confirmed playing (`pcm0p state: RUNNING`,
48000 Hz S16_LE stereo). This is what the codec looks like when it *works*.

Getting it cost the pmOS install: booting Android formats userdata. Restored
afterwards from `backups/*-2026-09-18.img.gz`. Do not repeat this lightly - the
files here are the point of that exercise.

| file | what |
|---|---|
| `codec_reg-idle.txt` | all 666 codec (PGD) registers, nothing playing |
| `codec_reg-PLAYING.txt` | playing to the **loudspeaker** (RX7 path) |
| `codec_reg-HPH-PLAYING.txt` | playing to **headphones** - the path we care about |
| `ifd-idle.txt`, `ifd-PLAYING.txt`, `ifd-HPH-PLAYING.txt` | interface device, 0x00-0xBF, via downstream's `peek` |
| `tinymix-*.txt` | every mixer control, same three states |
| `hw_params-PLAYING.txt`, `dmesg-HPH-PLAYING.txt` | stream params and kernel log |

Addresses in `codec_reg-*` are 4 hex digits (`01ab: 80`); the `ifd-*` files are
3 (`080: 0x20`).

## The two findings that matter

**1. The interface device never overflows - and it is completely static.**
`ifd-idle` and `ifd-HPH-PLAYING` are byte-identical:

    030: 0xff  031: 0xff  032: 0xff     interrupt enables
    040: 0x5   041: 0x5                 port cfg: watermark | ENABLE
    080: 0x20  081: 0x20                per-port status
    034: 0x0   060: 0x0   061: 0x0      no status, no source - no overflow, ever

Ours sits permanently at `034 = 0x01/0x03` with `0x01` (OVERFLOW) in the source
registers, and our per-port status reads **0x42** where downstream reads **0x20**.
That per-port byte is the one concrete difference in port state we have found.

**2. `SLIM_0_RX Channels = Two`.** The full working routing is otherwise exactly
what we already set by hand -

    SLIMBUS_0_RX Audio Mixer MultiMedia1 = On
    SLIM RX1 MUX = AIF1_PB      SLIM RX2 MUX = AIF1_PB
    RX1 MIX1 INP1 = RX1         RX2 MIX1 INP1 = RX2
    RX1 INTERP = RX1 MIX2       RX2 INTERP = RX2 MIX2
    CLASS_H_DSM MUX = DSM_HPHL_RX1
    HPHL DAC Switch = On

- except for `SLIM_0_RX Channels`, which downstream sets to **Two** and whose
default is **One**. That is the DSP-side SLIMbus channel count. A port fed by a
different number of channels than it is configured for is exactly what an
overflow is. **Untested against our driver at the time of writing.**

## Digital side matches, analog side does not

Ours already agrees on everything digital: `CLK_RX_B1_CTL=0x03`,
`CONN_RX1_B1_CTL=0x05`, `CONN_RX2_B1_CTL=0x06`, `CONN_RX_SB_B1_CTL=0x0a`
(confirming the value `0063` produces).

What we never set, from the 53-register idle->HPH diff:

    030c A_CDC_CLK_OTHR_CTL        0x00 -> 0x01   charge pump
    0181 A_BUCK_MODE_1             0x21 -> 0xa5   buck enable
    0192 A_NCP_EN                  0xfe -> 0xff   NCP enable
    0194 A_NCP_STATIC              0x28 -> 0x08
    0320 A_CDC_CLSH_B1_CTL         0xe4 -> 0xaf   Class-H, plus B2/B3/
    0321..0331                                    BUCK_NCP_VARS, thresholds,
                                                  K_DATA, I_PA_FACT, V_PA_*
    01a2 A_RX_COM_BIAS             0x00 -> 0x80
    01ab A_RX_HPH_CNP_EN           0x80 -> 0xb0   (ours reaches only 0xa0)
    02b7 A_CDC_RX1_VOL_CTL_B2_CTL  0x00 -> 0xfe   (ours 0x15)
    0363/0364 A_CDC_PA_RAMP_B3/B4  0x00 -> 0x36/0xc0
    0110 A_LDO_H_MODE_1            0x6d -> 0xed

Note the analog set was replayed by hand on our driver earlier, correctly
ordered, and did **not** clear the overflow - so it is necessary for audibility
but is not the cause of the port fault. Chase finding 1 and 2 first.
