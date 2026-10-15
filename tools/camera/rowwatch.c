/*
 * Stream from a camss video node and record, for every frame, its sequence
 * number, timestamp and a row profile (the mean of every 16th byte of each
 * line). A frame that lands shifted in its buffer shows up as a rotated
 * profile, so a whole run can be checked for when frames go out of place
 * and whether they come back. Set the pipeline up first (capture.sh with 1
 * frame does it); analyse with rowwatch.py on the host.
 *
 *   rowwatch /dev/videoN frames bytesperline height out.bin
 *
 * Each record: u32 sequence, u32 bytesused, u64 timestamp (us), then
 * height u16 row means (x16).
 *
 * Build on the phone: gcc -O2 -o rowwatch rowwatch.c
 */
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define T V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE
#define NBUF 4

int main(int argc, char **argv)
{
	if (argc < 6) {
		fprintf(stderr, "usage: rowwatch dev frames bpl height out\n");
		return 2;
	}
	int frames = atoi(argv[2]), bpl = atoi(argv[3]), h = atoi(argv[4]);
	int fd = open(argv[1], O_RDWR);
	FILE *out = fopen(argv[5], "wb");
	struct v4l2_requestbuffers rb = { .count = NBUF, .type = T, .memory = V4L2_MEMORY_MMAP };
	uint8_t *p[NBUF];
	uint16_t *prof = malloc(h * sizeof(*prof));

	if (fd < 0 || !out || ioctl(fd, VIDIOC_REQBUFS, &rb) || rb.count < 2) {
		perror("setup");
		return 1;
	}
	for (unsigned int i = 0; i < rb.count; i++) {
		struct v4l2_plane pl = { 0 };
		struct v4l2_buffer b = { .type = T, .memory = V4L2_MEMORY_MMAP, .index = i,
					 .m.planes = &pl, .length = 1 };

		if (ioctl(fd, VIDIOC_QUERYBUF, &b)) {
			perror("querybuf");
			return 1;
		}
		p[i] = mmap(NULL, pl.length, PROT_READ, MAP_SHARED, fd, pl.m.mem_offset);
		if (ioctl(fd, VIDIOC_QBUF, &b)) {
			perror("qbuf");
			return 1;
		}
	}
	int type = T;
	if (ioctl(fd, VIDIOC_STREAMON, &type)) {
		perror("streamon");
		return 1;
	}
	for (int n = 0; n < frames; n++) {
		struct v4l2_plane pl = { 0 };
		struct v4l2_buffer b = { .type = T, .memory = V4L2_MEMORY_MMAP,
					 .m.planes = &pl, .length = 1 };

		if (ioctl(fd, VIDIOC_DQBUF, &b)) {
			perror("dqbuf");
			return 1;
		}
		for (int y = 0; y < h; y++) {
			const uint8_t *row = p[b.index] + (size_t)y * bpl;
			unsigned int s = 0, c = 0;

			for (int x = 0; x < bpl; x += 16, c++)
				s += row[x];
			prof[y] = s * 16 / c;
		}
		uint32_t hdr[2] = { b.sequence, pl.bytesused };
		uint64_t ts = b.timestamp.tv_sec * 1000000ull + b.timestamp.tv_usec;

		fwrite(hdr, sizeof(hdr), 1, out);
		fwrite(&ts, sizeof(ts), 1, out);
		fwrite(prof, sizeof(*prof), h, out);
		ioctl(fd, VIDIOC_QBUF, &b);
	}
	ioctl(fd, VIDIOC_STREAMOFF, &type);
	fclose(out);
	return 0;
}
