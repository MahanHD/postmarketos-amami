#!/bin/sh
# Long GPU soak under Xorg: Megapixels 30 s, 5 s off, glxgears 20 s, repeated
# [cycles] times (default 60, about an hour). Logs the running hang count.
# Run it on the phone with: sudo systemd-run --uid=mahan ~/gpu-soak.sh 60
export DISPLAY=:0 XAUTHORITY=/home/mahan/.Xauthority
LOG=/home/mahan/gpu-soak.log
START=$(date '+%Y-%m-%d %H:%M:%S')
echo "start $START" > $LOG
i=0
while [ $i -lt ${1:-60} ]; do
	i=$((i+1))
	timeout 30 megapixels >/dev/null 2>&1
	sleep 5
	timeout 20 glxgears >/dev/null 2>&1
	sleep 3
	n=$(journalctl -k --since "$START" --no-pager | grep -c "hangcheck detected")
	echo "$(date +%T) cycle $i hangs $n" >> $LOG
done
echo done >> $LOG
