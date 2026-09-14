#!/bin/sh
# Measure suspended draw without a coulomb counter.
#
# The trap: "capacity" here is OCV-derived from instantaneous voltage, so it moves
# with *load*, not just with charge - the pack read 79% while charging and 61% a
# minute later under a 400 mA load, same charge. So comparing a reading taken under
# awake load against one taken straight out of suspend (battery rested, voltage
# recovered) would be meaningless, and could even show suspend "gaining" charge.
#
# So every endpoint is read at the SAME load state: awake, screen off, after a fixed
# settle. Then dV over the suspend window is comparable with dV over the awake
# window, and the awake window's current is known because the IADC can be sampled
# directly. The suspend figure is the awake one scaled by the ratio of the drops.
D=/sys/bus/iio/devices/iio:device0
B=/sys/class/power_supply/smbb-bif
OUT=/tmp/s2idle
PHASE=${1:-2400}
SETTLE=${2:-180}

rm -rf $OUT; mkdir -p $OUT
say() { echo "$(date +%s) $*" >> $OUT/log; }
uV() { cat $B/voltage_now; }
snap() { echo "$1 t=$(date +%s) cap=$(cat $B/capacity) uV=$(uV) bl=$(cat /sys/class/backlight/*/bl_power 2>/dev/null | head -1) i0=$(cat $D/in_current0_raw) i1=$(cat $D/in_current1_raw)" >> $OUT/log; }

screen_off() {
    su mahan -c "DISPLAY=:0 XAUTHORITY=/home/mahan/.Xauthority xset dpms force off" 2>/dev/null
}

# Sample through a settle so it can be checked that voltage actually flattened,
# rather than assuming 180 s was enough.
settle() {
    screen_off
    n=0
    while [ $n -lt $SETTLE ]; do
        echo "$1,$(date +%s),$(uV),$(cat $D/in_current1_raw),$(cat /sys/class/backlight/*/bl_power 2>/dev/null | head -1)" >> $OUT/settle.csv
        sleep 15; n=$((n+15))
    done
}

echo "tag,t,uV,i1,bl" > $OUT/settle.csv
echo "t,cap,uV,bl,i0,i1" > $OUT/awake.csv

say "=== settle 0: reach the awake screen-off load state ==="
settle pre_A
snap V0

say "=== PHASE A: awake, screen off, ${PHASE}s, IADC sampled ==="
end=$(( $(date +%s) + PHASE ))
while [ "$(date +%s)" -lt "$end" ]; do
    echo "$(date +%s),$(cat $B/capacity),$(uV),$(cat /sys/class/backlight/*/bl_power 2>/dev/null | head -1),$(cat $D/in_current0_raw),$(cat $D/in_current1_raw)" >> $OUT/awake.csv
    sleep 20
done
snap V1

say "=== PHASE B: suspend ${PHASE}s ==="
cat /sys/power/suspend_stats/success > $OUT/susp_before 2>/dev/null
rtcwake -m mem -s "$PHASE" >> $OUT/log 2>&1
snap wake_immediate
cat /sys/power/suspend_stats/success > $OUT/susp_after 2>/dev/null

say "=== settle 1: back to the same load state before reading V2 ==="
settle post_B
snap V2

say "=== DONE ==="
