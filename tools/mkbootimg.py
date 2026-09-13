#!/usr/bin/env python3
"""Build a boot image this device's bootloader will take.

S1Boot wants a plain Android boot image, header v0, 2048-byte pages. `boot-deploy`
writes one too, but with its own `quiet splash plymouth...` command line, so the
image has to be built by hand to keep the parameters the port depends on.

How far this is verified, precisely. The *logic* here was proven byte-exact: an
earlier build of the r56 image reproduced what was actually on the boot partition,
md5 69b89a70e0a216cc128579bea40f5561. This file is a tidied rewrite of that, and it
has been checked to emit the same header - every load address, the page size, the
kernel blob length (6513518, matching r56's own header) and the command line all
match - but **not** re-confirmed byte-for-byte, because that needs the phone's
/boot/initramfs and the phone was off.

So: first time this is used for real, rebuild the currently flashed kernel with it
and compare md5 against the boot partition before trusting it with anything else.
If that ever stops matching, suspect this file before suspecting the flash.

The kernel blob is zImage with the amami dtb appended - S1Boot does not take a
separate dtb - and both come out of the kernel apk:

    tar xzf linux-postmarketos-qcom-msm8974-6.16.12-rNN.apk -C apk/
      apk/boot/vmlinuz
      apk/boot/dtbs/qcom-msm8974-sony-xperia-rhine-amami.dtb

The initramfs must come from the phone, not the apk, and must match the kernel
package installed there - `apk add` regenerates /boot/initramfs, so pull it *after*
installing:

    ssh mahan@<phone> 'cat /boot/initramfs' > initramfs

Usage:
    mkbootimg.py --kernel apk/boot/vmlinuz \\
                 --dtb apk/boot/dtbs/qcom-msm8974-sony-xperia-rhine-amami.dtb \\
                 --initramfs initramfs -o boot.img [--extra-cmdline "..."]
"""

import argparse
import hashlib
import struct

# From the header of the image S1Boot was already booting. Do not guess these.
KERNEL_ADDR = 0x10008000
RAMDISK_ADDR = 0x12000000
SECOND_ADDR = 0x10F00000
TAGS_ADDR = 0x11E00000
PAGE_SIZE = 2048

# plymouth.enable=0     - plymouth wedges the boot on this device
# msm.vram / carveout   - keep even when an IOMMU is in use: if it fails to probe,
#                         msm_use_mmu() goes false and this is the fallback that
#                         still gives a display instead of nothing
# panic_on_rcu_stall +  - the panic net, so an unattended wedge reboots and leaves
# panic=10                a pstore record instead of hanging forever
# rcu_exp_cpu_stall_timeout - MILLISECONDS, unlike its sibling which is seconds.
#                         The default of 20 fires on the harmless ~3-jiffy
#                         expedited stall this device emits at ~36 s of every boot.
BASE_CMDLINE = (
    "plymouth.enable=0 msm.vram=192m msm.allow_vram_carveout=1 "
    "sysctl.kernel.panic_on_rcu_stall=1 panic=10 "
    "rcupdate.rcu_exp_cpu_stall_timeout=21000"
)

# These identify the rootfs to the initramfs; they are this phone's partitions.
UUID_CMDLINE = (
    "pmos_boot_uuid=12380e93-bad4-4a1f-8668-10e3f0f4a8d7 "
    "pmos_root_uuid=50036a41-7c6e-42e4-a53f-3a61d1f7abc6 "
    "pmos_rootfsopts=defaults"
)


def pad(blob):
    rem = len(blob) % PAGE_SIZE
    return blob + (b"\0" * (PAGE_SIZE - rem) if rem else b"")


def build(kernel, dtb, initramfs, extra_cmdline=""):
    kernel = kernel + dtb
    cmdline = BASE_CMDLINE
    if extra_cmdline:
        cmdline += " " + extra_cmdline.strip()
    cmdline += " " + UUID_CMDLINE
    cmdline = cmdline.encode()
    if len(cmdline) >= 512:
        raise SystemExit("cmdline is %d bytes; the header field holds 512" % len(cmdline))

    sha = hashlib.sha1()
    for blob in (kernel, initramfs, b""):
        sha.update(blob)
        sha.update(struct.pack("<I", len(blob)))

    hdr = b"ANDROID!"
    hdr += struct.pack(
        "<10I",
        len(kernel), KERNEL_ADDR,
        len(initramfs), RAMDISK_ADDR,
        0, SECOND_ADDR,
        TAGS_ADDR, PAGE_SIZE, 0, 0,
    )
    hdr += b"\0" * 16                                   # product name
    hdr += cmdline + b"\0" * (512 - len(cmdline))
    hdr += sha.digest() + b"\0" * 12                    # id[8], only sha1 used
    hdr += b"\0" * 1024                                 # extra cmdline

    return pad(hdr) + pad(kernel) + pad(initramfs), cmdline.decode()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--kernel", required=True, help="vmlinuz (zImage) from the apk")
    p.add_argument("--dtb", required=True, help="amami dtb from the apk")
    p.add_argument("--initramfs", required=True, help="/boot/initramfs pulled from the phone")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--extra-cmdline", default="",
                   help='e.g. "no_hash_pointers" or "arm-smmu.disable_bypass=0"')
    args = p.parse_args()

    img, cmdline = build(open(args.kernel, "rb").read(),
                         open(args.dtb, "rb").read(),
                         open(args.initramfs, "rb").read(),
                         args.extra_cmdline)
    open(args.output, "wb").write(img)
    print("%s  %d bytes" % (args.output, len(img)))
    print("cmdline: %s" % cmdline)


if __name__ == "__main__":
    main()
