#!/bin/sh
# Save every devcoredump (GPU hang dumps) before the kernel drops it, which it
# does five minutes after the hang. It turns on msm's rd_full first, so each
# dump carries every buffer of the job that hung. Dumps go to
# ~mahan/devcore/<boot>/<time>-<devcd>.devcore, each with a .txt note of the
# uptime and CMA state. Only the first MAX of a boot are kept, since a GPU that
# cannot recover hangs every two seconds; the rest are counted in count.txt
# and released unread so the next hang can produce a new one.
# Installed by devcore-collect.service; for a one-off run:
#   sudo systemd-run --unit=devcore ~/devcore-collect.sh
MAX=${MAX:-25}
BOOT=$(cut -c1-8 /proc/sys/kernel/random/boot_id)
OUT=/home/mahan/devcore/$(date +%Y%m%d-%H%M%S)-$BOOT
echo Y > /sys/module/msm/parameters/rd_full
n=0
while true; do
	for d in /sys/class/devcoredump/devcd*; do
		[ -e "$d/data" ] || continue
		# made with the first dump, so a boot without hangs leaves nothing
		[ -d $OUT ] || { mkdir -p $OUT; chown mahan: /home/mahan/devcore $OUT; }
		n=$((n + 1))
		if [ $n -le $MAX ]; then
			f=$OUT/$(date +%H%M%S)-$(basename $d)
			cat "$d/data" > "$f.devcore"
			{ cat /proc/uptime; grep -E "Cma|MemFree" /proc/meminfo; } > "$f.txt"
			chown mahan: "$f.devcore" "$f.txt"
		fi
		echo 1 > "$d/data"
		echo $n > $OUT/count.txt
	done
	sleep 5
done
