/*
 * Does the VFE write past a capture buffer? Map four buffers, fill the two
 * that are never queued with 0xa5, queue two, take one frame and count the
 * canary bytes that changed. With SETBUF=wpl,height in the environment, write
 * a WR_BUFFER_CFG into the write master after STREAMON (IMGSIZE=1 also sets
 * the image size, LINEBASED=1 switches it to line-based). COUNT sets the number
 * of buffers (full-size frames fit only two) and SAVE=file stores the frame.
 * Set the pipeline up as capture.sh does first. Build on the phone with
 * gcc -O2 -o canary canary.c (gcc, musl-dev, linux-headers).
 * Usage: canary /dev/videoN
 */
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define T V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE

static void set_buffer_cfg(const char *s)
{
	unsigned int wpl, h, n;
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	volatile uint32_t *m = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0xfda10000);

	sscanf(s, "%u,%u", &wpl, &h);
	for (n = 0; n < 7; n++) {
		volatile uint32_t *b = m + (0x6c + 0x24 * n) / 4;
		if (b[0] & 2) {
			b[6] = (wpl << 16) | ((h - 1) << 4) | 3;
			if (getenv("IMGSIZE"))	/* also the line-based image size */
				b[5] = (((wpl + 1) / 2 - 1) << 16) | (h - 1);
			if (getenv("LINEBASED"))
				b[0] &= ~2u;
			m[0x4c / 4] = 1u << n;	/* reload the write master */
			printf("wm%u ping %08x pong %08x buf %08x\n", n, b[1], b[2], b[6]);
		}
	}
}

int main(int argc, char **argv)
{
	int fd = open(argv[1], O_RDWR);
	struct v4l2_requestbuffers rb = { .count = getenv("COUNT") ? atoi(getenv("COUNT")) : 4, .type = T, .memory = V4L2_MEMORY_MMAP };
	struct v4l2_plane pl[1];
	struct v4l2_buffer b;
	uint8_t *p[4];
	size_t len[4];
	unsigned int i, k;
	struct pollfd pfd = { .fd = fd, .events = POLLIN };

	unsigned int nb = rb.count;
	if (ioctl(fd, VIDIOC_REQBUFS, &rb) || rb.count < nb) { printf("reqbufs %u\n", rb.count); return 1; }
	for (i = 0; i < nb; i++) {
		memset(&b, 0, sizeof(b)); memset(pl, 0, sizeof(pl));
		b.type = T; b.memory = V4L2_MEMORY_MMAP; b.index = i; b.m.planes = pl; b.length = 1;
		ioctl(fd, VIDIOC_QUERYBUF, &b);
		len[i] = pl[0].length;
		p[i] = mmap(NULL, len[i], PROT_READ | PROT_WRITE, MAP_SHARED, fd, pl[0].m.mem_offset);
		memset(p[i], 0xa5, len[i]);
		if (i < 2 && ioctl(fd, VIDIOC_QBUF, &b)) { perror("qbuf"); return 1; }
	}
	printf("buffer length %zu\n", len[0]);
	int t = T;
	if (ioctl(fd, VIDIOC_STREAMON, &t)) { perror("streamon"); return 1; }
	if (getenv("SETBUF")) set_buffer_cfg(getenv("SETBUF"));
	if (poll(&pfd, 1, 5000) <= 0) { printf("no frame\n"); goto out; }
	memset(&b, 0, sizeof(b)); memset(pl, 0, sizeof(pl));
	b.type = T; b.memory = V4L2_MEMORY_MMAP; b.m.planes = pl; b.length = 1;
	ioctl(fd, VIDIOC_DQBUF, &b);
	printf("frame in buffer %u, bytesused %u, flags %x\n", b.index, pl[0].bytesused, b.flags);
	usleep(300000);
	if (getenv("SAVE")) {
		FILE *f = fopen(getenv("SAVE"), "wb");
		fwrite(p[b.index], 1, len[b.index], f);
		fclose(f);
	}
	for (i = 0; i < nb; i++) {
		size_t changed = 0, first = (size_t)-1;
		for (k = 0; k < len[i]; k++)
			if (p[i][k] != 0xa5) { changed++; if (first == (size_t)-1) first = k; }
		printf("buffer %u: %zu of %zu bytes changed%s\n", i, changed, len[i], i < 2 ? " (queued)" : " (canary)");
	}
out:
	ioctl(fd, VIDIOC_STREAMOFF, &t);
	return 0;
}
