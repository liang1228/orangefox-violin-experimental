#!/system/bin/sh
# Offline candidate: full OS3 HAL, root, private C++ runtime. Foreground only.
set -eu
export TMPDIR=/tmp
[ "$(id -u)" = 0 ]
[ "$(getprop ro.product.device)" = violin ]
[ "$(getprop init.svc.recovery)" = running ]

# All daemon scratch files must stay in the recovery RAM filesystem.
if awk '$2 ~ /^\/data(\/|$)/ || $2 ~ /^\/vendor(\/|$)/ || $2 ~ /^\/odm(\/|$)/ || $2 ~ /^\/mnt\/vendor\/persist(\/|$)/ { found=1 } END { exit !found }' /proc/mounts; then
    echo 'Refusing touch diagnostic with data/vendor/odm/persist mounted.' >&2
    exit 1
fi
sha256sum -c /system/etc/violin-touchfeature.sha256
if pidof touch_report_debug >/dev/null; then
    echo 'Debug THP already running; do not start two raw-frame consumers.' >&2
    exit 1
fi
if pidof vendor.xiaomi.hw.touchfeature-service >/dev/null; then
    echo 'Full touchfeature service already running.'
    exit 0
fi
[ -c /dev/binder ]
[ "$(getprop init.svc.violin-servicemanager)" = running ]
sh /system/bin/load-violin-touch.sh
[ -c /dev/xiaomi-touch ]

# The public driver reloads firmware on this write, even when raw is enabled.
# Skip if already 1; otherwise write once per boot, never in a polling loop.
raw=/sys/class/touch/touch_dev/enable_touch_raw
[ -e "$raw" ]
if [ ! -e /tmp/violin-touch-raw.initialized ]; then
    if [ "$(cat "$raw")" != 1 ]; then
        printf '1\n' > "$raw"
    fi
    printf 'initialized\n' > /tmp/violin-touch-raw.initialized
fi
mkdir -p /data/vendor/touch /data/vendor/touch_state /data/vendor/bsplog/touch /data/vendor/mqsas_common
export LD_LIBRARY_PATH=/odm/lib64/touchfeature:/system/lib64:/vendor/lib64:/odm/lib64
exec /system/bin/vendor.xiaomi.hw.touchfeature-service >> /tmp/violin-touchfeature.log 2>&1
