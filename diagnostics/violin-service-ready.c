/* Check registration only. Never invoke a key-service method or read keys. */
#include <android/binder_ibinder.h>
#include <android/binder_manager.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 3) return 64;
    char *end = NULL;
    long seconds = strtol(argv[1], &end, 10);
    if (!end || *end || seconds < 1 || seconds > 60) return 64;
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return 1;
    time_t deadline = now.tv_sec + seconds;
    do {
        int ready = 1;
        for (int i = 2; i < argc; ++i) {
            AIBinder *binder = AServiceManager_checkService(argv[i]);
            if (!binder || !AIBinder_isAlive(binder)) ready = 0;
            if (binder) AIBinder_decStrong(binder);
        }
        if (ready) return 0;
        usleep(200000);
        if (clock_gettime(CLOCK_MONOTONIC, &now)) return 1;
    } while (now.tv_sec < deadline);
    fprintf(stderr, "Timed out waiting for Binder registration\n");
    return 1;
}
