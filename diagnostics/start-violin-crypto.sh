#!/system/bin/sh
# Startup integration probe: no userdata/metadata mount or key retrieval.
set -eu
export TMPDIR=/tmp
export PATH=/system/bin:/sbin
[ "$(id -u)" = 0 ]
[ "$(getprop ro.product.device)" = violin ]
[ "$(getprop sys.boot_completed)" != 1 ]
[ "$(getprop init.svc.violin-crypto-bootstrap)" = running ]
exec >> /tmp/violin-crypto-startup.log 2>&1

stage() {
    setprop sys.orangefox.crypto.stage "$1"
    echo "crypto startup: $1"
}
finish() {
    result=$?
    trap - EXIT
    if [ "$result" != 0 ]; then
        setprop sys.orangefox.crypto.services_ready 0
        echo "crypto startup failed at $(getprop sys.orangefox.crypto.stage): exit $result"
    fi
    # init's stopped trigger also releases the GUI after a hard timeout.
    setprop ctl.start recovery
    exit "$result"
}
trap finish EXIT

stage integrity
sha256sum -c /system/etc/violin-services.sha256
[ "$(getprop ro.build.version.release)" = 16 ]
[ "$(getprop ro.build.version.security_patch)" = 2026-09-01 ]
[ "$(getprop ro.vendor.build.security_patch)" = 2026-09-01 ]
[ "$(getprop ro.hardware.gatekeeper)" = mitee ]
[ "$(getprop ro.boot.mitee_disable)" != true ]

stage touch-ram-view
/system/bin/violin-touch-mountns --capture /tmp/violin-touch-view
setprop ctl.start violin-servicemanager
setprop ctl.start violin-touchfeature
/system/bin/violin-service-ready 20 vendor.xiaomi.hw.touchfeature.ITouchFeature/default

stage persist
[ -b /dev/block/by-name/persist ]
mkdir -p /mnt/vendor/persist
# Preserve the real TEE backing store; never substitute an empty RAM directory.
# This is a read-write service integration test, not a read-only TEE test.
mount -t ext4 -o noatime,nosuid,nodev,barrier=1 /dev/block/by-name/persist /mnt/vendor/persist
[ -d /mnt/vendor/persist/data ]
[ -d /mnt/vendor/persist/fdsd ]

stage tee-devices
[ -c /dev/tee0 ]
[ -c /dev/teepriv0 ]
[ -c /dev/rpmb0 ]
for node in /dev/tee0 /dev/teepriv0 /dev/rpmb0 /dev/mmcblk0rpmb /dev/0:0:0:49476 /dev/ufs-bsg0; do
    if [ -c "$node" ]; then
        chown system:system "$node"
        chmod 0660 "$node"
    fi
done
setprop ctl.start violin-tee
setprop ctl.start violin-keymint
setprop ctl.start violin-gatekeeper

stage security-registration
/system/bin/violin-service-ready 25 \
    android.hardware.security.keymint.IKeyMintDevice/default \
    android.hardware.security.sharedsecret.ISharedSecret/default \
    android.hardware.security.secureclock.ISecureClock/default \
    android.hardware.gatekeeper.IGatekeeper/default

stage keystore-registration
setprop ctl.start keystore2
/system/bin/violin-service-ready 15 android.system.keystore2.IKeystoreService/default
setprop sys.orangefox.crypto.services_ready 1
stage services-registered
# Registration is not a successful getSecurityLevel, key unwrap or data unlock.
