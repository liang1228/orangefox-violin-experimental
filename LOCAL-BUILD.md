# Local OrangeFox source setup

`setup-local-orangefox.sh` prepares a separate OrangeFox 12.1 source tree in
`/root/orangefox-violin-20261103/source` on the current machine's WSL Ubuntu.
It uses the same pinned OrangeFox sync script as the Actions build, limits the
download to four parallel jobs, and avoids the upstream helper's shared
`/tmp/recovery` path. The source tree must not already exist.

After a successful sync, the script checks the recovery commit used by the
Actions build and saves two source inventories alongside the source tree. The
raw `manifest-pinned.xml` incorrectly describes the replaced recovery checkout
as TeamWin and omits `vendor/recovery`; do not use it to restore the tree. The
corrected inventory records the actual OrangeFox URLs and revisions. It is not
a complete build recipe: the pinned upstream sync script applies additional
patches, and the local build script applies the single-plane display change.

`build-local-orangefox.sh` copies the tracked violin device tree into the
isolated source and builds `recoveryimage` with four jobs. It records output in
`/root/orangefox-violin-20261103/build-local.log`. A successful build is not
proof of real-device compatibility. Neither script flashes or reboots a device.

The device-specific source and build configuration are maintained in this
private repository. Large Android/OrangeFox upstream source trees, proprietary
firmware, and personal device logs are not committed here.
