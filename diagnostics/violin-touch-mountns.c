/* Keep the early RAM touch environment visible after /data is mounted.
 * Run from init before mounting userdata, then pass the existing launcher.
 * This does not create cgroup isolation; init must still own the service.
 */
#define _GNU_SOURCE
#include <limits.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <unistd.h>

static const char *paths[] = {"/data", "/vendor", "/odm", "/mnt/vendor/persist"};
static const char *names[] = {"data", "vendor", "odm", "persist"};
#define VIEW_COUNT (sizeof(paths) / sizeof(paths[0]))

static int ram_path(const char *path) {
    struct statfs fs;
    return statfs(path, &fs) == 0 &&
           ((unsigned long)fs.f_type == 0x01021994UL ||
            (unsigned long)fs.f_type == 0x858458f6UL);
}

static int mounted(const char *path, int descendants) {
    FILE *fp = fopen("/proc/self/mounts", "r");
    char line[8192], target[PATH_MAX];
    if (!fp) return -1;
    int found = 0;
    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, "%*s %4095s", target) != 1) continue;
        size_t len = strlen(path);
        if (!strcmp(path, target) ||
            (descendants && !strncmp(path, target, len) && target[len] == '/')) {
            found = 1;
            break;
        }
    }
    fclose(fp);
    return found;
}

/* Retain RAM bind mounts in init's namespace so an init-managed restart can
 * recover the same view even after the parent mounts data or persist. */
static int capture(const char *view) {
    if (!ram_path("/tmp")) return 1;
    for (size_t i = 0; i < VIEW_COUNT; ++i) {
        if (!ram_path(paths[i]) || mounted(paths[i], 1) != 0) {
            fprintf(stderr, "Refusing non-early RAM path: %s\n", paths[i]);
            return 1;
        }
    }
    if (mkdir(view, 0700) != 0) return 1;
    size_t completed = 0;
    char target[PATH_MAX];
    for (size_t i = 0; i < VIEW_COUNT; ++i) {
        if (snprintf(target, sizeof(target), "%s/%s", view, names[i]) >= (int)sizeof(target)) goto failed;
        if (mkdir(target, 0700) != 0 || mount(paths[i], target, NULL, MS_BIND | MS_REC, NULL) != 0) goto failed;
        ++completed;
        if (mount(NULL, target, NULL, MS_PRIVATE | MS_REC, NULL) != 0) goto failed;
    }
    return 0;
failed:
    while (completed) {
        --completed;
        snprintf(target, sizeof(target), "%s/%s", view, names[completed]);
        umount2(target, MNT_DETACH);
    }
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 2 || getuid() != 0) {
        fprintf(stderr, "usage (root): violin-touch-mountns PROGRAM [ARG ...]\n");
        return 64;
    }
    if (argc == 3 && !strcmp(argv[1], "--capture")) return capture(argv[2]);
    const char *view = NULL;
    int program = 1;
    if (argc >= 4 && !strcmp(argv[1], "--ram-view")) {
        view = argv[2];
        program = 3;
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
    if (view) {
        char source[PATH_MAX];
        for (size_t i = 0; i < VIEW_COUNT; ++i) {
            if (snprintf(source, sizeof(source), "%s/%s", view, names[i]) >= (int)sizeof(source) ||
                !ram_path(source) || mounted(source, 0) != 1 ||
                mount(source, paths[i], NULL, MS_BIND | MS_REC, NULL) != 0) {
                fprintf(stderr, "Unable to restore RAM view: %s\n", names[i]);
                return 1;
            }
        }
        if (setenv("VIOLIN_TOUCH_RAM_VIEW", "1", 1) != 0) return 1;
    }
    execvp(argv[program], argv + program);
    perror("touch exec");
    return 1;
}
