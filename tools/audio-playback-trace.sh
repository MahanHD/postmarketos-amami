#!/bin/sh
# Load the codec and run two playbacks: the RX port status (INT_STATUS_RX_0/1) during
# and after each, and every non-register SLIMbus message the NGD sends (kprobe).
# Run as root on a fresh boot; the sound daemons are frozen so the first run is the first.
R=/sys/kernel/debug/regmap/217:a0:0:0/registers
T=/sys/kernel/tracing
rd() { grep -E '^03[45]:' $R | tr '\n' ' '; }
pkill -STOP -x pulseaudio; pkill -STOP -x pipewire; pkill -STOP -x wireplumber
echo '-:slimx' >> $T/kprobe_events 2>/dev/null
echo 'p:slimx slim_qcom_ngd_ctrl:qcom_slim_ngd_xfer_msg mt=+1(%r1):u8 mc=+2(%r1):x8 la=+7(%r1):x8 n=+2(+8(%r1)):u8 w0=+0(+8(+8(%r1))):x32 w1=+4(+8(+8(%r1))):x32' >> $T/kprobe_events
echo 'mt != 0 || mc < 0x60' > $T/events/kprobes/slimx/filter
echo 1 > $T/events/kprobes/slimx/enable; echo 1 > $T/tracing_on
modprobe snd-soc-wcd9320
for i in $(seq 30); do [ -e /proc/asound/card0 ] && break; sleep 1; done
sleep 2
amixer -q -c 0 cset name='SLIMBUS_0_RX Audio Mixer MultiMedia1' 1
amixer -q -c 0 cset name='SLIM RX1 MUX' AIF1_PB
amixer -q -c 0 cset name='SLIM RX2 MUX' AIF1_PB
amixer -q -c 0 cset name='RX1 MIX1 INP1' RX1
amixer -q -c 0 cset name='RX2 MIX1 INP1' RX2
amixer -q -c 0 cset name='RX1 INTERP' 'RX1 MIX2'
amixer -q -c 0 cset name='CLASS_H_DSM MUX' DSM_HPHL_RX1
amixer -q -c 0 cset name='HPHL DAC Switch' 1
amixer -q -c 0 cset name='HPHL Volume' 70%
for run in 1 2; do
  echo "== playback $run, before: $(rd)"
  timeout 3 speaker-test -D hw:0,0 -c 2 -r 48000 -F S16_LE -t sine >/dev/null 2>&1 &
  for i in 1 2 3 4; do sleep 0.5; echo "  $(grep state /proc/asound/card0/pcm0p/sub0/status) $(rd)"; done
  wait
  sleep 7   # past pmdown_time, so POST_PMD has run
  echo "   after stop: $(rd)"
done
grep -v '^#' $T/trace | sed 's/.*slimx: ([^)]*)//'
echo 0 > $T/events/kprobes/slimx/enable; echo '-:slimx' >> $T/kprobe_events
dmesg | grep -E "overflow error|wait timeout|TX timed out|slim|wcd9320" | grep -v "WCD:" | tail -20
pkill -CONT -x pulseaudio; pkill -CONT -x pipewire; pkill -CONT -x wireplumber
