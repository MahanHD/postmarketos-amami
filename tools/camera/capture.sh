#!/bin/sh
# Capture RAW10 frames from the rear IMX200 with the imx200 driver. Run as root
# on the phone. After a stream that fails or times out, the next one tends to
# wedge camss; after good ones, several streams per boot work.
#
#   capture.sh [frames] [exposure] [analogue_gain] [test_pattern]
#
# SIZE picks the sensor mode: 5248x3936 (default), 2624x1976, 2624x1480 or
# 1312x988. Writes OUT (default /home/mahan/capture.raw, packed RAW10) and a log.
# FOCUS=0..1023 sets the lens (higher is closer; about 256 for distant scenes,
# 512 for near objects); without it the lens stays unpowered at rest.
# The camera modules are loaded with --ignore-install, so this works with the
# bring-up blacklist in place. See docs/notes.md, "Camera".
set -u
OUT=${OUT:-/home/mahan/capture.raw}; LOG=${OUT%.raw}.log
CNT=${1:-4}; EXPO=${2:-1200}; AGAIN=${3:-128}; TP=${4:-0}
SIZE=${SIZE:-5248x3936}; W=${SIZE%x*}; H=${SIZE#*x}
: > "$LOG"

modprobe --ignore-install i2c_qcom_cci
modprobe imx200
modprobe bu64296
modprobe --ignore-install qcom_camss
for i in $(seq 30); do [ -e /dev/media0 ] && break; sleep 1; done

M=/dev/media0
if [ -n "${FOCUS:-}" ]; then
	LENS=$(media-ctl -d $M -e "bu64296 3-000c")
	# the lens stays powered only while its node is open
	exec 3<>"$LENS"
	v4l2-ctl -d "$LENS" -c focus_absolute="$FOCUS"
	sleep 0.2
fi

SENSOR="imx200 3-0010"
S=$(media-ctl -d $M -e "$SENSOR")
V=$(media-ctl -d $M -e msm_vfe0_video0)
F="SRGGB10_1X10/${W}x${H} field:none"

media-ctl -d $M -l '"msm_csiphy0":1->"msm_csid0":0[1],"msm_csid0":1->"msm_ispif0":0[1],"msm_ispif0":1->"msm_vfe0_rdi0":0[1]'
media-ctl -d $M -V "\"$SENSOR\":0[fmt:$F],\"msm_csiphy0\":0[fmt:$F],\"msm_csid0\":0[fmt:$F],\"msm_ispif0\":0[fmt:$F],\"msm_vfe0_rdi0\":0[fmt:$F]"
v4l2-ctl -d "$V" --set-fmt-video=width=$W,height=$H,pixelformat=pRAA
v4l2-ctl -d "$S" -c test_pattern=$TP
v4l2-ctl -d "$S" -c exposure=$EXPO,analogue_gain=$AGAIN

timeout 60 v4l2-ctl -d "$V" --stream-mmap=2 --stream-count="$CNT" --stream-to="$OUT" 2>>"$LOG"
echo "size=$SIZE bytes=$(stat -c %s "$OUT")" >> "$LOG"
sync
