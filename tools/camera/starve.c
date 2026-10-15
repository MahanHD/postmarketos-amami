/*
 * Stream from a camss video node with a reader too slow for it, so that the
 * VFE runs out of buffers, then read normally and save the last frame. Shows
 * whether frames still land aligned after buffer starvation. Set the
 * pipeline up first (capture.sh with 1 frame does it).
 *
 *   starve /dev/videoN [held_frames] [hold_ms] [out.raw]
 *
 * COUNT buffers (default 3) are queued; each of the first held_frames
 * (default 60) is kept hold_ms (default 200) before it is queued again.
 * Then 10 frames are read without delay and the last one is saved.
 *
 * Build on the phone: gcc -O2 -o starve starve.c
 */
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define T V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE

int main(int argc, char **argv)
{
	int held = argc > 2 ? atoi(argv[2]) : 60;
	int hold_ms = argc > 3 ? atoi(argv[3]) : 200;
	const char *out = argc > 4 ? argv[4] : "/tmp/starve.raw";
	int fd = open(argv[1], O_RDWR);
	struct v4l2_requestbuffers rb = { .count = getenv("COUNT") ? atoi(getenv("COUNT")) : 3,
					  .type = T, .memory = V4L2_MEMORY_MMAP };
	void *p[16];
	unsigned int len[16];

	if (fd < 0 || ioctl(fd, VIDIOC_REQBUFS, &rb) || rb.count < 2) {
		perror("reqbufs");
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
		len[i] = pl.length;
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
	unsigned int last = 0, seq0 = 0, seq = 0;
	for (int n = 0; n < held + 10; n++) {
		struct v4l2_plane pl = { 0 };
		struct v4l2_buffer b = { .type = T, .memory = V4L2_MEMORY_MMAP,
					 .m.planes = &pl, .length = 1 };

		if (ioctl(fd, VIDIOC_DQBUF, &b)) {
			perror("dqbuf");
			return 1;
		}
		if (n == 0)
			seq0 = b.sequence;
		seq = b.sequence;
		if (n < held)
			usleep(hold_ms * 1000);
		last = b.index;
		if (n == held + 9)
			break;
		ioctl(fd, VIDIOC_QBUF, &b);
	}
	FILE *f = fopen(out, "wb");
	fwrite(p[last], 1, len[last], f);
	fclose(f);
	printf("frames %d, sequence %u..%u\n", held + 10, seq0, seq);
	ioctl(fd, VIDIOC_STREAMOFF, &type);
	return 0;
}
