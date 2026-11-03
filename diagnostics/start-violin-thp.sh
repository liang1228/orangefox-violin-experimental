#!/system/bin/sh
# Foreground runtime diagnostic. All supplied files must be from OS3.0.305.
# Does not fix the kernel tp_raw bounds warning or establish physical touch.
set -eu
export TMPDIR=/tmp

[ "$(id -u)" = 0 ]
[ "$(getprop ro.product.device)" = violin ]
[ "$(getprop init.svc.recovery)" = running ]

# This diagnostic uses only the recovery RAM filesystem. Refuse a mounted
# userdata/vendor/odm rather than writing the daemon's scratch files there.
if awk '$2 == "/data" || $2 == "/vendor" || $2 == "/odm" || $2 == "/vendor/odm" { found=1 } END { exit !found }' /proc/mounts; then
    echo 'Expected unmounted data/vendor/odm for this RAM diagnostic.' >&2
    exit 1
fi

sha256sum -c /system/etc/violin-thp.sha256
if pidof touch_report_debug >/dev/null; then
    echo 'touch_report_debug is already running; inspect its log/frame flow.'
    exit 0
fi

sh /system/bin/load-violin-touch.sh
mkdir -p /data/vendor/touch /data/vendor/bsplog/touch
export LD_LIBRARY_PATH=/odm/lib64
exec /system/bin/touch_report_debug 0
