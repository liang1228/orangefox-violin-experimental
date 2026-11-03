#!/usr/bin/env bash
# Build a local diagnostic recovery. This script does not touch the tablet.
set -eo pipefail

base=/root/orangefox-violin-20261103
source_dir="$base/source"
repo_dir=/mnt/e/workspace/projects/xiaomi-root/analysis_outputs/orangefox-violin-actions
expected_recovery=6bd902d14f754ab98a7cccc5598f7b9d135cfc38
test -d "$base"
rm -f "$base/build-exit-code.txt"
exec > "$base/build-local.log" 2>&1
trap 'code=$?; printf "%s\n" "$code" > "$base/build-exit-code.txt"' EXIT
renice -n 10 -p "$$" >/dev/null
mkdir -p "$base/bin"
if [[ ! -e "$base/bin/python" ]]; then
    ln -s "$(command -v python3)" "$base/bin/python"
fi
export PATH="$base/bin:$PATH"

test "$(git -C "$source_dir/bootable/recovery" rev-parse HEAD)" = "$expected_recovery"
test -d "$source_dir/vendor/recovery"
test -d "$repo_dir/device/xiaomi/violin"
mkdir -p "$source_dir/device/xiaomi"
if [[ -e "$source_dir/device/xiaomi/violin" ]]; then
    diff -qr "$repo_dir/device/xiaomi/violin" "$source_dir/device/xiaomi/violin" >/dev/null || {
        echo 'The existing violin tree differs; refusing to overwrite it.' >&2
        exit 1
    }
else
    cp -a "$repo_dir/device/xiaomi/violin" "$source_dir/device/xiaomi/violin"
fi
python3 - "$source_dir/bootable/recovery/minuitwrp/graphics_drm.cpp" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
old = '#define DEFAULT_NUM_LMS 2'
new = '#define DEFAULT_NUM_LMS 1'
assert (text.count(old), text.count(new)) in ((1, 0), (0, 1))
if old in text:
    path.write_text(text.replace(old, new))
PY
cd "$source_dir"
set +e
source build/envsetup.sh
setup_result=$?
set -e
# OrangeFox's optional setup may return nonzero even when lunch is installed.
type lunch >/dev/null || { echo "envsetup failed: $setup_result" >&2; exit 1; }
export ALLOW_MISSING_DEPENDENCIES=true
lunch twrp_violin-eng
m -j4 recoveryimage
test -f out/target/product/violin/recovery.img
sha256sum out/target/product/violin/recovery.img
echo 'Local experimental build complete; no device boot has been verified.'
