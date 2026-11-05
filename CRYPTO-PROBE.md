# OS3 internal-storage prerequisites: offline probe

Status: 2026-11-05. Firmware: **OS3.0.305.0.WOTCNXM**. No tablet was
connected for the final checks. These results do **not** establish decryption,
internal-storage MTP, a successful new-image boot, or touch after mounting data.
The user reports no screen-lock credential; the first runtime path should use
that condition, without requesting a password or assuming it removes encryption.

## Verified on the build computer

| Check | Result |
| --- | --- |
| Recovery build with FBE/metadata flags | Exit 0, approximately 6 minutes 15 seconds |
| Built Recovery and keystore2 ELF closures | No missing libraries or unresolved strong dynamic symbols |
| Matching OS3 tee-supplicant, KeyMint and Gatekeeper closures | All three pass after supplying the matching system library |
| ARM64 touch namespace helper | Compiles with NDK 29; ELF closure passes |
| Private mount namespace, synthetic host test | Child keeps RAM view while parent sees the test userdata mount |
| Slave mount namespace, negative control | Child incorrectly sees test userdata; regression rejects it |
| Wrong firmware | Rejected before output creation |
| Existing audit evidence | Rejected without overwriting it |
| BoardConfig after probe | Restored and compared with the canonical non-crypto profile |

The matching system partition supplies `libapexsupport.so`, which was absent
from the initial vendor/Recovery-only audit. Its SHA256 is
`8dd03a6843753884bdaa6a95f25c04c4051bc5ab5f9ea6e7343012f2a0384c3c`.
This closes the three audited programs' static dependency/symbol sets. It does
not test linker namespaces, C++ ABI behavior, Binder registration, TA loading,
secure-world operations, or access to existing encrypted data. Proprietary
libraries and firmware are not included in this repository.

The compile probe uses the pinned Recovery source
`6bd902d14f754ab98a7cccc5598f7b9d135cfc38` and temporarily adds:

```make
TW_INCLUDE_CRYPTO := true
TW_INCLUDE_CRYPTO_FBE := true
BOARD_USES_METADATA_PARTITION := true
```

Built Recovery SHA256:
`fff8b7ef28b58cd96aa35df5f9d5e4be441632993f332d1174e9d60441143e5e`.
This is a compile probe, **not** the V5 executable and not a device-ready
recovery image. The build system's ordinary raw image/ZIP output has not been
adapted or approved for this tablet.

## Keep touch alive when real data is mounted

The current touch environment uses early RAM paths under `/data`. Mounting
the real encrypted filesystem over those paths could hide its models/scratch.
`diagnostics/violin-touch-mountns.c` creates a private mount namespace and then
executes the original launcher. It must start **before** the real data mount.
It changes mount propagation only; init still needs to own the service so USB
restarts do not kill it along with adbd.

The pinned Android init implementation uses recursive `MS_SLAVE` for
`namespace mnt`. That still receives parent mount events. The host regression
therefore starts with a shared parent mount, tests the private helper, and
tests a deliberately changed slave helper. Testing only a private parent
would incorrectly pass both implementations. All test mounts use synthetic
temporary directories inside a disposable host namespace, never a partition.

This helper is not wired into the candidate or deployed. The existing touch
launcher's mounted-data guard is retained. Startup ordering, Android runtime
behavior and service restart after data is mounted still require integration
and testing. Do not remove that guard just to make a later restart succeed.

## Reproduce the computer checks

The scripts use this project's existing WSL checkout and matching stock
extraction. They do not connect to a tablet:

```sh
bash diagnostics/build-crypto-probe.sh
python3 diagnostics/verify-crypto-probe.py \
  --probe /root/orangefox-violin-20261103/crypto-probe-20261104 \
  --stock-root /root/orangefox-violin-20261103/stock-thp-305 \
  --ndk /mnt/e/workspace/projects/xiaomi-root/ndk \
  --output /path/to/new/verification-directory
```

`build-crypto-probe.sh` deliberately refuses to reuse its existing evidence
directory. For another build, choose a new `result` path in the script; do not
delete the original evidence. It locks the build tree, checks the canonical
BoardConfig, and restores it only if the temporary profile is still its own.
The captured `compiled-root` remains available independently of later builds.

Restoring BoardConfig does **not** revert generated build outputs. After the
probe, `out/target/product/violin/recovery/root` contains the crypto build.
Do not package it as V5; the V5 packer checks its separate expected hash.

The Linux NDK was unpacked on Windows, leaving some executable aliases as
text files. The verifier invokes `clang-21` directly and creates a local
`ld.lld` symlink to the real `lld`; it does not modify the NDK installation.
The mount regression requires root and mount-namespace support in Linux/WSL.

## Runtime work still required

1. Integrate matching OS3 Mitee services, device permissions, trusted
   applications and an old-libvintf-compatible manifest. Passing ELF checks
   alone does not supply these.
2. Resolve the pinned decrypt path's HIDL Gatekeeper expectation against
   this firmware's AIDL Gatekeeper. The reported no-credential case is the
   first target; it does not validate PIN/password/pattern support.
3. Guard startup before testing existing metadata keys. The current Recovery
   can automatically enter its decrypt path, and the pinned metadata-key
   code can create directories or generate a key when retrieval fails.
   Running that path is not a read-only inspection.
4. With the tablet connected, verify real data mapping, file-key unlock,
   touch across mounting and USB switches, and a file round trip via MTP.
   None of these is established by this offline report.

Tablet user artifacts belong under the **real mounted internal storage's**
`Download/OrangeFox-violin`. Until that works, keep new artifacts on the
computer; do not create files in an unmounted `/sdcard` RAM directory.

## References

- [Skyward PR #1](https://github.com/kirklin/skyward/pull/1): service/touch
  reference; its Qualcomm secure stack is not the violin Mitee stack.
- [AOSP metadata encryption](https://source.android.com/docs/security/features/encryption/metadata):
  KeyMint readiness and the metadata-encryption prerequisite.
- [Android 12 init service utilities](https://github.com/aosp-mirror/platform_system_core/blob/android12-release/init/service_utils.cpp):
  mount namespace propagation behavior; compared with the local pinned source.
