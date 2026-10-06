#!/bin/sh
# Capture RAW10 frames from the rear IMX200. Run as root on the phone, once per
# boot (a second stream after a failed or timed-out one tends to wedge camss).
#
#   capture.sh [frames] [exposure] [analogue_gain] [test_pattern]
#
# Writes /home/mahan/capture.raw (packed RAW10, 6560 bytes per line) and a log.
# The camera modules are loaded with --ignore-install, so this works with the
# bring-up blacklist in place. See docs/notes.md, "Camera".
set -u
OUT=${OUT:-/home/mahan/capture.raw}; LOG=${OUT%.raw}.log
CNT=${1:-4}; EXPO=${2:-3976}; AGAIN=${3:-128}; TP=${4:-0}
W=5248; H=3936
: > "$LOG"

modprobe --ignore-install i2c_qcom_cci
modprobe --ignore-install ccs
modprobe --ignore-install qcom_camss
for i in $(seq 30); do [ -e /dev/media0 ] && break; sleep 1; done

M=/dev/media0
SENSOR="imx200 pixel_array 3-0010"
PA=$(media-ctl -d $M -e "$SENSOR")
V=$(media-ctl -d $M -e msm_vfe0_video0)
F="SRGGB10_1X10/${W}x${H} field:none"

media-ctl -d $M -l '"msm_csiphy0":1->"msm_csid0":0[1],"msm_csid0":1->"msm_ispif0":0[1],"msm_ispif0":1->"msm_vfe0_rdi0":0[1]'
media-ctl -d $M -V "\"$SENSOR\":0[crop:(0,0)/${W}x${H}]"
media-ctl -d $M -V "\"imx200 binner 3-0010\":0[fmt:SRGGB12_1X12/${W}x${H}]"
media-ctl -d $M -V "\"imx200 scaler 3-0010\":0[fmt:SRGGB12_1X12/${W}x${H}]"
media-ctl -d $M -V "\"imx200 scaler 3-0010\":1[fmt:$F],\"msm_csiphy0\":0[fmt:$F],\"msm_csid0\":0[fmt:$F],\"msm_ispif0\":0[fmt:$F],\"msm_vfe0_rdi0\":0[fmt:$F]"
v4l2-ctl -d "$V" --set-fmt-video=width=$W,height=$H,pixelformat=pRAA
v4l2-ctl -d "$PA" -c test_pattern=$TP
v4l2-ctl -d "$PA" -c exposure=$EXPO,analogue_gain=$AGAIN

timeout 60 v4l2-ctl -d "$V" --stream-mmap=2 --stream-count="$CNT" --stream-to="$OUT" 2>>"$LOG"
echo "bytes=$(stat -c %s "$OUT")" >> "$LOG"
sync
