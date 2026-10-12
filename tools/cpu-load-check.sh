#!/bin/sh
# Load every Krait core and check that it still computes correctly.
# One worker per core, pinned with taskset, hashes the same 32 MiB of
# random data over and over and compares each sum with a reference taken
# first. A wrong sum means a core is not getting the voltage its clock
# needs. Every 10 s it logs each core's frequency, the CPU temperatures
# and the mismatch count to ~/cpu-load-check.log.
# Run it on the phone with: sudo systemd-run ~/cpu-load-check.sh [minutes]
MIN=${1:-10}
LOG=/home/mahan/cpu-load-check.log
DIR=/dev/shm/cpu-load-check
mkdir -p $DIR
head -c 33554432 /dev/urandom > $DIR/data
REF=$(sha256sum $DIR/data | cut -d' ' -f1)
: > $DIR/bad
echo "start $(date +%T), $MIN min, reference $REF" > $LOG

END=$(( $(date +%s) + MIN * 60 ))
for c in 0 1 2 3; do
	(
		while [ $(date +%s) -lt $END ]; do
			s=$(taskset -c $c sha256sum $DIR/data | cut -d' ' -f1)
			[ "$s" = "$REF" ] || echo "cpu$c $(date +%T) $s" >> $DIR/bad
		done
	) &
done

while [ $(date +%s) -lt $END ]; do
	sleep 10
	f=""
	for c in 0 1 2 3; do
		f="$f $(cat /sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq 2>/dev/null || echo off)"
	done
	t=""
	for z in /sys/class/thermal/thermal_zone*; do
		case $(cat $z/type) in cpu*) t="$t $(cat $z/type)=$(( $(cat $z/temp) / 1000 ))";; esac
	done
	echo "$(date +%T) kHz$f |$t | bad $(wc -l < $DIR/bad)" >> $LOG
done
wait
echo "done, $(wc -l < $DIR/bad) wrong sums" >> $LOG
cat $DIR/bad >> $LOG
rm -r $DIR
