#!/bin/sh
# Save every devcoredump (GPU hang dumps) before the kernel drops it, which it
# does five minutes after the hang. Each dump goes to ~/devcore/<time>.devcore,
# then is released so the next hang can produce a new one.
# Run it on the phone with: sudo systemd-run --unit=devcore ~/devcore-collect.sh
OUT=/home/mahan/devcore
mkdir -p $OUT
while true; do
	for d in /sys/class/devcoredump/devcd*; do
		[ -e "$d/data" ] || continue
		f=$OUT/$(date +%Y%m%d-%H%M%S)-$(basename $d).devcore
		cat "$d/data" > "$f"
		echo 1 > "$d/data"
		chown mahan: "$f"
	done
	sleep 5
done
