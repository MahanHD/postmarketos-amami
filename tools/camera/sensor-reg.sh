#!/bin/sh
# Read or write IMX200 registers over CCI master 0 (/dev/i2c-3) while the
# sensor is powered, i.e. during a stream. Needs i2c-tools.
#
#   sensor-reg.sh 0202 0203        read registers (hex, 16-bit address)
#   sensor-reg.sh 0220=00          write a register
for a in "$@"; do
	r=${a%%=*}; hi=0x$(echo "$r" | cut -c1-2); lo=0x$(echo "$r" | cut -c3-4)
	case "$a" in
	*=*) i2ctransfer -f -y 3 w3@0x10 "$hi" "$lo" "0x${a#*=}" && echo "$r <- ${a#*=}" ;;
	*)   echo "$r = $(i2ctransfer -f -y 3 w2@0x10 "$hi" "$lo" r1)" ;;
	esac
done
