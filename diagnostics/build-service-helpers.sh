#!/bin/bash
set -euo pipefail
[ "$#" = 4 ] || { echo 'usage: build-service-helpers.sh NDK ANDROID_SOURCE CRYPTO_ROOT NEW_OUTPUT' >&2; exit 64; }
ndk=$(realpath "$1")
source=$(realpath "$2")
crypto=$(realpath "$3")
output=$4
[ ! -e "$output" ] || { echo 'Output already exists' >&2; exit 1; }
mkdir -p "$output"
output=$(realpath "$output")
here=$(cd "$(dirname "$0")" && pwd)
llvm=$ndk/toolchains/llvm/prebuilt/linux-x86_64
ln -s "$llvm/bin/lld" "$output/ld.lld"
flags=(--target=aarch64-linux-android31 --sysroot="$llvm/sysroot" --ld-path="$output/ld.lld" -O2 -Wall -Wextra -Werror)
"$llvm/bin/clang-21" "${flags[@]}" "$here/violin-touch-mountns.c" -o "$output/violin-touch-mountns"
"$llvm/bin/clang-21" "${flags[@]}" -I"$source/frameworks/native/libs/binder/ndk/include_platform" \
    "$here/violin-service-ready.c" "$crypto/system/lib64/libbinder_ndk.so" \
    -Wl,--allow-shlib-undefined -o "$output/violin-service-ready"
sha256sum "$output/violin-touch-mountns" "$output/violin-service-ready" > "$output/helpers.sha256"
