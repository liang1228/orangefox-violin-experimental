# Chinese UI, touch across USB switches, and MTP

Status: 2026-11-04, OS3.0.305.0.WOTCNXM. Live changes were RAM-only. The
candidate below has **not** been flashed or booted; its new executable has not
been run on the tablet. Firmware, models, images and full traces stay local.

## What was verified on the running tablet

- The user confirmed physical touch and position after the full OS3 touch HAL,
  base VINTF manifest, and XY-swap/Y-mirror input correction were loaded in RAM.
- Chinese resources from the pinned OrangeFox source were loaded without
  restarting the GUI. Simplified Chinese rendered correctly in the captured UI.
  A 60-second, 300-frame recording was captured and decoded successfully.
- Enabling MTP had killed the manually launched Binder manager and touch HAL:
  both inherited adbd's cgroup, which init kills when switching USB mode. They
  were moved to the root cgroup for this session. In the candidate they are
  init-managed services, independent of adbd; that startup still needs testing.
- FunctionFS MTP was absent. Creating its function and mount, waiting for both
  MTP/ADB descriptors, and binding both interfaces made Windows recognize MTP.
  A temporary RAM controller adapts the old, already-parsed init rules; the
  candidate instead imports `init.violin.mtp.rc` and removes the old handler
  that incorrectly mapped `mtp,adb` to ADB only.
- Windows Shell/WPD uploaded and downloaded a **4 MiB file with a Chinese
  filename** over MTP. Source, device and returned SHA256 matched. ADB was used
  only to verify the uploaded hash, not to carry either transfer.
- Three subsequent MTP off/on cycles preserved the same touch HAL and Binder
  manager. Injected Menu/Files taps passed after each cycle. Physical contact
  was not re-tested during these cycles; the GUI and tablet were not restarted.

The transfer used a clearly named RAM-only test directory. It was removed after
testing and is no longer exposed. It does **not** establish access to encrypted
internal storage. Per user preference, future tablet files belong under real
internal storage's `Download/OrangeFox-violin`, after it is unlocked and mounted.
Do not create a replacement directory on the unmounted `/sdcard` RAM path.

## Fixes in the compiled candidate

`violin-mtp-lifecycle.patch` changes only MTP child management:

- Reap the saved MTP PID before clearing it; the original `waitpid(0)` could
  reap a different child and leave MTP zombies.
- Detect a dead child rather than treating a nonzero cached PID as enabled.
- Wait for descriptors and USB composition, with a five-second bound and ADB
  fallback on failure. A successful fork alone is not MTP readiness.
- Close inherited GUI/input/DRM and command-pipe descriptors in the child.
  Inspection found the running old MTP child retaining the CLI output FIFO,
  explaining commands that executed but waited for EOF until MTP exited.
- Close the pipe even when the child was already reaped; do not send a signal
  to an already-reaped PID during failed startup cleanup.

The child-descriptor change is compatible with this pinned Bionic's `fork`,
which disables fdsan checks in the child. Compilation and static ELF checks
pass; runtime success and failure paths of this **new binary** remain untested.

Chinese uses the existing OrangeFox translation/font. The audit covers all
1,106 English keys with no missing placeholders; all 607 used CJK characters
exist in the font. Only an incorrect MD5 checkbox translation and two missing
keys were corrected. No translation or proprietary payload binary is published.

## Local build

The existing WSL source checkout and display/input patches are prerequisites.

```sh
bash diagnostics/build-zh-cn.sh
python3 diagnostics/prepare-zh-cn.py \
  --source /root/orangefox-violin-20261103/source/bootable/recovery \
  --output /path/to/new/chinese-resource-directory
# Use the touch packer's usual base/stock/input/avbtool/output arguments plus:
# --recovery-program .../out/target/product/violin/recovery/root/system/bin/recovery
# --chinese-root /path/to/new/chinese-resource-directory
```

The packer verifies exact input hashes and audits the new executable's ELF
closure. Neither command contacts or writes to a tablet. The resource stager
and packer require new output directories and preserve previous results.

Final local candidate: `FOX-ZH-MTP-V5-20261104/recovery.img`, under the project's
`outputs/orangefox-violin-20261103` directory.

| Check | Result |
| --- | --- |
| Final incremental build | Exit 0, 1 minute 11 seconds |
| Recovery executable SHA256 | `2daa3b1ae486ed8e0b0cfbc1f6599e4e14c59fc500ecdd802e5ad4794dc0b79a` |
| Candidate SHA256 | `3f3783413ee6115d985e73f5c8f0fd6d5db1ac815ac1937ea483e378f0b3d6d4` |
| Layout | 100 MiB, v4, ramdisk only, legacy LZ4 |
| Payload manifest | 39/39 file hashes pass |
| ELF closure | 9/9 checks pass, including the new Recovery binary |
| Init | Touch services and MTP rules accepted by host_init_verifier |
| Input | Actual C++ four-corner/center checks pass |
| AVB | Unsigned NONE footer/hash selfcheck passes, rollback 1788220800/location 11 |
| Cold boot / new-binary runtime | Not tested; not recommended for unattended flashing |

## Internal storage remains a separate prerequisite

The live build reports `ro.orangefox.crypto_enabled=0`. `/data` is unmounted,
no decrypted dm device exists, and `/sdcard` is only an unmounted RAM directory.
The stock fstab specifies FBE plus metadata encryption using `wrappedkey_v0`.
The matching OS3 vendor requires Xiaomi **Mitee**, not Qualcomm's secure stack:
`tee-supplicant`, KeyMint V3, shared-secret/secure-clock services and Gatekeeper.
The kernel's mitee module and `/dev/tee0`/`teepriv0` exist, but the userspace
service/unlock path is not integrated in this build.

An offline audit of the matching OS3 vendor found no missing dependency for
tee-supplicant; the KeyMint and Gatekeeper closures still lack
`libapexsupport.so` in the audited Recovery/vendor search paths. This is a
static result, not proof that adding one library would make decryption work.
No wrapped keys or credentials were read, secure services executed, userdata
formatted, encryption removed, or metadata changed during this inspection.

Do not relabel a RAM transfer as internal-storage acceptance. Internal file
transfer requires the matching secure stack, metadata mapping and file-key
unlock to work first. Pens, backup/restore, flashing and the previously observed
kernel THP bounds warning also remain outside this round's acceptance.

## References

- [Skyward PR #1](https://github.com/kirklin/skyward/pull/1), inspected at
  `97b8bd36e669a8ae72ec8ff64ea0b8c486f33e3f`: touch/service inspiration. The PR
  itself adds Qualcomm devices; their secure stack was not transplanted.
- [Skyward existing MTP init](https://github.com/huime180/skyward/blob/97b8bd36e669a8ae72ec8ff64ea0b8c486f33e3f/crates/skyward-pack/src/mtp.rc):
  FunctionFS setup and descriptor readiness. MTP was existing baseline code,
  not an addition in PR #1.
- [Pinned OrangeFox Chinese](https://gitlab.com/OrangeFox/bootable/Recovery/-/blob/6bd902d14f754ab98a7cccc5598f7b9d135cfc38/gui/theme/extra-languages/languages/zh_CN.xml).
- [AOSP metadata encryption](https://source.android.com/docs/security/features/encryption/metadata):
  KeyMint must be ready before the encrypted data filesystem is mounted.
