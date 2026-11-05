#!/system/bin/sh
# Runtime diagnostic for the verified OS3.0.305 violin modules, not an installer.
# This driver triggered a tp_raw bounds warning in the live test; see RECOVERY-CLI.md.
set -eu
# adbd inherits /data/local/tmp, which does not exist with userdata unmounted.
export TMPDIR=/tmp

[ "$(id -u)" = 0 ]
[ "$(getprop ro.product.device)" = violin ]
[ "$(getprop init.svc.recovery)" = running ] ||
    [ "$(getprop init.svc.violin-crypto-bootstrap)" = running ]
case "$(uname -r)" in
    6.6.118-android15-8-*) ;;
    *) echo 'Unsupported kernel for this diagnostic' >&2; exit 1 ;;
esac

modules=/lib/modules/6.6.118-android15-8-4k
spi=$modules/extra/xring-modules/drivers/spi/xr_spi_mmio.ko
common=$modules/extra/xiaomi-modules/touch_driver/o81a/xiaomi_touch_violin.ko
touch=$modules/extra/xiaomi-modules/touch_driver/o81a/nt36532_tc_touch.ko

# Check all prerequisites before loading anything. Firmware must be supplied
# separately from the user's matching system; it is not kept in this repository.
sha256sum -c <<EOF
18e26b401d138f34466ab84eeb27e6ce9c34420814e99a552a11a376c8c406cb  $spi
e083797e8fa2c626c736d91f4f6f4ebb33c236e68efbbdb99b324bb58a53bf8d  $common
2418a4d605f0e95d7db0c2998648eb76b72a206627b5ac5aecd0b33b56a09af7  $touch
3effd0693bcd0277940e1b468b98feebffc2e03501d06eb26902d9fd1831185c  /odm/firmware/novatek_nt36536_violin_fw_tm00.bin
3effd0693bcd0277940e1b468b98feebffc2e03501d06eb26902d9fd1831185c  /odm/firmware/novatek_nt36536_violin_fw_tm01.bin
3effd0693bcd0277940e1b468b98feebffc2e03501d06eb26902d9fd1831185c  /odm/firmware/novatek_nt36536_violin_fw_tm02.bin
EOF

if ! grep -q '^xr_spi_mmio ' /proc/modules; then
    insmod "$spi"
fi
if ! grep -q '^xiaomi_touch_violin ' /proc/modules; then
    insmod "$common"
fi
if ! grep -q '^nt36532_tc_touch ' /proc/modules; then
    insmod "$touch"
fi

attempt=0
while [ "$attempt" -lt 15 ]; do
    if grep -q NVTCapacitiveTouchScreen /proc/bus/input/devices &&
       [ -r /proc/nvt_fw_version ] &&
       grep -q 'fw_ver=23,' /proc/nvt_fw_version; then
        cat /proc/nvt_fw_version
        echo 'Touch initialized only; driver bounds warning and physical taps remain unresolved.'
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
done
echo 'Touch initialization did not reach the expected firmware state.' >&2
exit 1
