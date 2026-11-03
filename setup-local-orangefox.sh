#!/usr/bin/env bash
# Set up a separate local OrangeFox 12.1 source tree for violin experiments.
set -euo pipefail

base=/root/orangefox-violin-20261103
sync_dir="$base/fox-sync"
source_dir="$base/source"
repo_bin="$base/bin/repo"
sync_commit=03434a833701f73430cd085738ae0bf54f2231f1
recovery_commit=6bd902d14f754ab98a7cccc5598f7b9d135cfc38

if [[ -e "$source_dir" ]]; then
    echo "Refusing to replace existing source tree: $source_dir" >&2
    exit 1
fi
mkdir -p "$base/bin"
if [[ ! -d "$sync_dir/.git" ]]; then
    git clone https://gitlab.com/OrangeFox/sync.git "$sync_dir"
fi
git -C "$sync_dir" checkout --detach "$sync_commit"
test "$(git -C "$sync_dir" rev-parse HEAD)" = "$sync_commit"
curl -fLS --retry 3 https://storage.googleapis.com/git-repo-downloads/repo -o "$repo_bin"
chmod 0755 "$repo_bin"
export PATH="$base/bin:$PATH"
export REPO_SYNC_JOBS=4

# The upstream helper unconditionally deletes /tmp/recovery. Give this run its
# own temp path, and limit sync concurrency to keep memory and bandwidth bounded.
python3 - "$sync_dir/orangefox_sync.sh" "$sync_dir/orangefox_sync_local.sh" "$base" <<'PY'
import pathlib, sys
source, target, base = map(pathlib.Path, sys.argv[1:])
text = source.read_text()
assert text.count('/tmp/recovery') == 3
assert text.count('mv recovery /tmp;') == 1
assert text.count('-j$(nproc --all)') == 1
text = text.replace('/tmp/recovery', str(base / 'tmp-recovery'))
text = text.replace('mv recovery /tmp;', f'mv recovery {base / "tmp-recovery"};')
text = text.replace('-j$(nproc --all)', '-j4')
target.write_text(text)
PY
cd "$sync_dir"
bash ./orangefox_sync_local.sh --branch 12.1 --path "$source_dir"
test -d "$source_dir/vendor/twrp"
test -d "$source_dir/vendor/recovery"
test "$(git -C "$source_dir/bootable/recovery" rev-parse HEAD)" = "$recovery_commit"
cd "$source_dir"
repo manifest -r -o "$base/manifest-pinned.xml"
git -C vendor/recovery rev-parse HEAD > "$base/vendor-recovery-commit.txt"
printf 'Local sources synced; device tree and build still require setup.\n'
