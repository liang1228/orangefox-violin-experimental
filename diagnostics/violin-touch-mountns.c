/* Keep the early RAM touch environment visible after /data is mounted.
 * Run from init before mounting userdata, then pass the existing launcher.
 * This does not create cgroup isolation; init must still own the service.
 */
#define _GNU_SOURCE
#include <sched.h>
#include <stdio.h>
#include <sys/mount.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 2 || getuid() != 0) {
        fprintf(stderr, "usage (root): violin-touch-mountns PROGRAM [ARG ...]\n");
        return 64;
    }
    if (unshare(CLONE_NEWNS) != 0) {
        perror("touch unshare");
        return 1;
    }
    /* init's namespace mnt uses MS_SLAVE: later parent mount events still
     * arrive there. MS_PRIVATE also blocks the incoming /data overmount.
     */
    if (mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) != 0) {
        perror("touch private mounts");
        return 1;
    }
    execvp(argv[1], argv + 1);
    perror("touch exec");
    return 1;
}
