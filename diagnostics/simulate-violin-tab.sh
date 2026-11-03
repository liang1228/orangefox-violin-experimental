#!/system/bin/sh
# Synthetic input for the tested 3200x2136 diagnostic UI; no hardware touch test.
set -eu
[ "$(id -u)" = 0 ]
[ "$(getprop ro.product.device)" = violin ]
[ "$(getprop init.svc.recovery)" = running ]
[ "$(cat /sys/class/input/event3/device/name)" = NVTCapacitiveTouchScreen ]

case "${1:-}" in
    menu) raw_x=179943 ;;
    files) raw_x=33786 ;;
    *) echo 'Usage: sh simulate-violin-tab.sh menu|files (unlocked UI only)' >&2; exit 1 ;;
esac
raw_y=302762
event=/dev/input/event3
send() { sendevent "$event" "$1" "$2" "$3"; }
release() {
    send 3 58 0
    send 3 48 0
    send 1 330 0
    # minuitwrp requires negative tracking ID after the zero pressure/major.
    send 3 57 -1
    send 0 0 0
}
trap release EXIT
send 3 47 0
send 3 57 1000
send 1 330 1
send 3 58 1
send 3 48 20
# Force both coordinates to be emitted even after an identical previous tap.
send 3 53 "$((raw_x - 1))"
send 3 54 "$((raw_y - 1))"
send 3 53 "$raw_x"
send 3 54 "$raw_y"
send 0 0 0
sleep 0.15
