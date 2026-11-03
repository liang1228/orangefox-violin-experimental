# Local OrangeFox source setup

`setup-local-orangefox.sh` prepares a separate OrangeFox 12.1 source tree in
`/root/orangefox-violin-20261103/source` on the current machine's WSL Ubuntu.
It uses the same pinned OrangeFox sync script as the Actions build, limits the
download to four parallel jobs, and avoids the upstream helper's shared
`/tmp/recovery` path. The source tree must not already exist.

After a successful sync, the script checks the recovery commit used by the
working Actions build and saves a pinned repo manifest and the vendor-recovery
commit alongside the source tree. Other OrangeFox sync patches remain local;
review their changes before treating the manifest as a fully reproducible build.
The script does not configure the violin device tree, compile, flash, or upload
source trees or firmware images. Those steps and real-device compatibility must
be verified separately.

The device-specific source and build configuration are maintained in this
private repository. Large Android/OrangeFox upstream source trees, proprietary
firmware, and personal device logs are not committed here.
