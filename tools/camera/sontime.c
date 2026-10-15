/*
 * Time VIDIOC_STREAMON (the sensor's enable_streams: mode, shading table and
 * control writes) and the first frame on a camss video node already set up
 * (capture.sh with 1 frame does it).
 *
 *   sontime /dev/videoN [runs]
 *
 * Build on the phone: gcc -O2 -o sontime sontime.c
 */
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <time.h>
#define T V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1e3 + t.tv_nsec / 1e6; }
int main(int argc, char **argv)
{
	int fd = open(argv[1], O_RDWR), n = argc > 2 ? atoi(argv[2]) : 5;
	for (int r = 0; r < n; r++) {
		struct v4l2_requestbuffers rb = { .count = 2, .type = T, .memory = V4L2_MEMORY_MMAP };
		if (ioctl(fd, VIDIOC_REQBUFS, &rb)) { perror("reqbufs"); return 1; }
		for (unsigned i = 0; i < rb.count; i++) {
			struct v4l2_plane pl = { 0 };
			struct v4l2_buffer b = { .type = T, .memory = V4L2_MEMORY_MMAP, .index = i, .m.planes = &pl, .length = 1 };
			ioctl(fd, VIDIOC_QBUF, &b);
		}
		int type = T;
		double a = now();
		if (ioctl(fd, VIDIOC_STREAMON, &type)) { perror("streamon"); return 1; }
		double b = now();
		struct v4l2_plane pl = { 0 };
		struct v4l2_buffer bf = { .type = T, .memory = V4L2_MEMORY_MMAP, .m.planes = &pl, .length = 1 };
		ioctl(fd, VIDIOC_DQBUF, &bf);
		double c = now();
		printf("streamon %.0f ms, first frame after %.0f ms\n", b - a, c - a);
		ioctl(fd, VIDIOC_STREAMOFF, &type);
		rb.count = 0; ioctl(fd, VIDIOC_REQBUFS, &rb);
	}
	return 0;
}
