#!/usr/bin/env bash
# Compile-only FBE feasibility probe. Never runs programs on the tablet.
# The resulting root is NOT a device-ready image: Mitee services and modern
# Gatekeeper compatibility still require integration and runtime validation.
set -eo pipefail
base=/root/orangefox-violin-20261103
repo=/mnt/e/workspace/projects/xiaomi-root/analysis_outputs/orangefox-violin-actions
result="$base/crypto-probe-20261104"
if test "$#" -ne 0; then
    if test "$#" -ne 2 || test "$1" != --result; then
        echo 'usage: build-crypto-probe.sh [--result NEW_DIRECTORY]' >&2
        exit 64
    fi
    result="$2"
fi
mkdir -p "$result"
exec 9>"$base/violin-build.lock"
flock -n 9
test ! -e "$result/BoardConfig.original.mk"
exec > "$result/build.log" 2>&1
renice -n 10 -p "$$" >/dev/null
cd "$base/source"
test "$(git -C bootable/recovery rev-parse HEAD)" = 6bd902d14f754ab98a7cccc5598f7b9d135cfc38
test "$(git -C system/vold rev-parse HEAD)" = a164ba05c5fef288059774a776b2e6e1119957cf
for name in violin-default-password violin-metadata-existing-key violin-keymaster-no-upgrade; do
    patch_file="$repo/diagnostics/$name.patch"
    if git -C system/vold apply --check "$patch_file" >/dev/null 2>&1; then
        git -C system/vold apply "$patch_file"
    else
        git -C system/vold apply --reverse --check "$patch_file"
    fi
done
board=device/xiaomi/violin/BoardConfig.mk
cmp "$board" "$repo/device/xiaomi/violin/BoardConfig.mk"
cp "$board" "$result/BoardConfig.original.mk"
cat "$board" > "$result/BoardConfig.crypto.mk"
cat >> "$result/BoardConfig.crypto.mk" <<'EOF'

# Compile probe only; this profile is never installed or used by packaging.
TW_INCLUDE_CRYPTO := true
TW_INCLUDE_CRYPTO_FBE := true
BOARD_USES_METADATA_PARTITION := true
EOF
cleanup() {
    code=$?
    if cmp -s "$board" "$result/BoardConfig.crypto.mk"; then
        cp "$result/BoardConfig.original.mk" "$board"
    else
        echo 'BoardConfig changed concurrently; original retained in probe directory.' >&2
        code=1
    fi
    printf '%s\n' "$code" > "$result/exit-code.txt"
    exit "$code"
}
trap cleanup EXIT
cp "$result/BoardConfig.crypto.mk" "$board"
export PATH="$base/bin:$PATH"
set +e
source build/envsetup.sh
set -e
export ALLOW_MISSING_DEPENDENCIES=true
lunch twrp_violin-eng
python3 "$repo/diagnostics/test-crypto-unlock.py" \
    --vold-source "$base/source/system/vold" --output "$result/unlock-regression"
git -C system/vold diff -- Decrypt.cpp MetadataCrypt.cpp KeyStorage.cpp > "$result/vold.diff"
m -j4 recoveryimage
cp -a out/target/product/violin/recovery/root "$result/compiled-root"
sha256sum "$result/compiled-root/system/bin/recovery" > "$result/recovery.sha256"
echo 'Compile probe finished. No tablet operation or device-ready image produced.'
