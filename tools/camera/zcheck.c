/*
 * Allocate camss buffers (REQBUFS and mmap, no streaming) and count the
 * nonzero bytes in each: fresh buffers must come back zeroed (0118).
 *
 *   zcheck /dev/videoN count
 *
 * Build on the phone: gcc -O2 -o zcheck zcheck.c
 */
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#define T V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE
int main(int argc, char **argv)
{
	int fd = open(argv[1], O_RDWR);
	struct v4l2_requestbuffers rb = { .count = atoi(argv[2]), .type = T, .memory = V4L2_MEMORY_MMAP };
	if (fd < 0 || ioctl(fd, VIDIOC_REQBUFS, &rb)) { perror("reqbufs"); return 1; }
	for (unsigned i = 0; i < rb.count; i++) {
		struct v4l2_plane pl = { 0 };
		struct v4l2_buffer b = { .type = T, .memory = V4L2_MEMORY_MMAP, .index = i, .m.planes = &pl, .length = 1 };
		if (ioctl(fd, VIDIOC_QUERYBUF, &b)) { perror("querybuf"); return 1; }
		unsigned char *p = mmap(NULL, pl.length, PROT_READ, MAP_SHARED, fd, pl.m.mem_offset);
		if (p == MAP_FAILED) { perror("mmap"); return 1; }
		size_t nz = 0;
		for (size_t j = 0; j < pl.length; j++) nz += p[j] != 0;
		printf("buffer %u: %u bytes, %zu nonzero\n", i, pl.length, nz);
		munmap(p, pl.length);
	}
	return 0;
}
