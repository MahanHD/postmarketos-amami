#!/bin/sh
# Offline and online cores 1-3 in turn, N cycles; log every step to disk.
N=${1:-60}; L=/home/mahan/hotplug-stress.log; : > $L
for i in $(seq $N); do
	for c in 1 2 3; do
		echo 0 > /sys/devices/system/cpu/cpu$c/online || echo "cycle $i cpu$c offline FAILED" >> $L
		sleep 0.2
		echo 1 > /sys/devices/system/cpu/cpu$c/online || echo "cycle $i cpu$c online FAILED" >> $L
	done
	echo "cycle $i online=$(cat /sys/devices/system/cpu/online)" >> $L; sync
done
echo END >> $L; sync
