#!/usr/bin/env bash
# Dedicated violin checkout only. Builds a library; never accesses a device.
set -eo pipefail
base=/root/orangefox-violin-20261103
repo=/mnt/e/workspace/projects/xiaomi-root/analysis_outputs/orangefox-violin-actions
cd "$base/source"
exec > "$base/build-skyward-input.log" 2>&1
trap 'code=$?; printf "%s\n" "$code" > "$base/build-skyward-input-exit.txt"' EXIT
renice -n 10 -p "$$" >/dev/null
test "$(git -C bootable/recovery rev-parse HEAD)" = 6bd902d14f754ab98a7cccc5598f7b9d135cfc38
grep -qx '#define DEFAULT_NUM_LMS 1' bootable/recovery/minuitwrp/graphics_drm.cpp
patch_file="$repo/diagnostics/violin-skyward-input.patch"
if git -C bootable/recovery apply --check "$patch_file"; then
    git -C bootable/recovery apply "$patch_file"
else
    git -C bootable/recovery apply --reverse --check "$patch_file"
fi
python3 "$repo/diagnostics/check-input-mapping.py" bootable/recovery
export PATH="$base/bin:$PATH"
set +e
source build/envsetup.sh
set -e
type lunch >/dev/null
export ALLOW_MISSING_DEPENDENCIES=true
lunch twrp_violin-eng
m -j4 libminuitwrp
sha256sum out/target/product/violin/system/lib64/libminuitwrp.so
echo 'Library build complete; physical orientation is not verified.'
