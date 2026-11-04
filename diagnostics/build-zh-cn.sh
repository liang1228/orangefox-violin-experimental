#!/usr/bin/env bash
# Build the pinned OrangeFox with its existing Chinese translation and font.
# No device commands; the finished image is adapted and checked separately.
set -eo pipefail
base=/root/orangefox-violin-20261103
repo=/mnt/e/workspace/projects/xiaomi-root/analysis_outputs/orangefox-violin-actions
exec > "$base/build-zh-cn.log" 2>&1
trap 'code=$?; printf "%s\n" "$code" > "$base/build-zh-cn-exit.txt"' EXIT
renice -n 10 -p "$$" >/dev/null
cd "$base/source"
test "$(git -C bootable/recovery rev-parse HEAD)" = 6bd902d14f754ab98a7cccc5598f7b9d135cfc38
grep -qx '#define DEFAULT_NUM_LMS 1' bootable/recovery/minuitwrp/graphics_drm.cpp
python3 "$repo/diagnostics/check-input-mapping.py" bootable/recovery
patch_file="$repo/diagnostics/violin-mtp-lifecycle.patch"
if git -C bootable/recovery apply --check "$patch_file"; then
    git -C bootable/recovery apply "$patch_file"
else
    git -C bootable/recovery apply --reverse --check "$patch_file"
fi
python3 - "$repo/device/xiaomi/violin/BoardConfig.mk" device/xiaomi/violin/BoardConfig.mk <<'PY'
from pathlib import Path
import sys
desired, current = map(Path, sys.argv[1:])
new = desired.read_text()
old = current.read_text()
language = 'TW_EXTRA_LANGUAGES := true\nTW_DEFAULT_LANGUAGE := zh_CN\n'
mtp = '# This diagnostic\'s USB init supports ADB only; MTP has no working endpoint.\nTW_EXCLUDE_MTP := true\n'
assert new.count(language) == 1 and mtp not in new
assert old in (new, new + mtp, new.replace(language, ''), new.replace(language, language + mtp)), 'Unexpected local board changes'
current.write_text(new)
PY
export PATH="$base/bin:$PATH"
set +e
source build/envsetup.sh
set -e
type lunch >/dev/null
export ALLOW_MISSING_DEPENDENCIES=true
lunch twrp_violin-eng
m -j4 recoveryimage
sha256sum out/target/product/violin/recovery/root/system/bin/recovery \
    out/target/product/violin/system/lib64/libminuitwrp.so
echo 'Chinese build finished; no device reboot or flash performed.'
