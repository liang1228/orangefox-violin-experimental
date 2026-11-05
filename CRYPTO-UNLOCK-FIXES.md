# No-credential unlock source fixes

Status: 2026-11-05. Matching firmware: **OS3.0.305.0.WOTCNXM**.
These are source fixes and computer-side tests. The new Recovery executable
has not run on the tablet, and Recovery decryption/internal-storage MTP are
not yet accepted.

## Three defects fixed

1. **Partially initialized default credential token.** The pinned vold fork
   copied the 16-byte `default-password` into a 32-byte uninitialized array.
   Its remaining bytes then contributed to the application ID. Android 16's
   no-credential/no-password-data path instead zero-pads to 32 bytes. The
   patch clears the array before the existing copy; it does not change the
   password-based scrypt path or claim support for every legacy protector.
2. **Directory creation when only an existing metadata key is allowed.**
   Recovery already passes `needs_encrypt=false`, selecting `neverGen()`.
   Therefore key generation was already disabled for this call; describing
   it as automatic key generation was too broad. However, `read_key()` still
   called `MkdirsSync()` before retrieval. The new `!gen.allow_gen` branch
   checks for an existing directory and retrieves the existing key, or
   refuses without creating a directory. Provisioning behavior is retained
   when generation is explicitly requested.
3. **Unchecked absent upgraded key blob.** `KeymasterOperation` returns an
   optional upgraded blob. The fork had commented out its empty check, then
   unconditionally dereferenced it even when no upgrade was needed. The
   patch restores the early return. Successful ordinary operations therefore
   do not dereference an absent optional or try to write an upgraded blob.

These fixes do not make the whole unlock process read-only. Existing-key
retrieval still contacts secure hardware, and the pinned code has RAM scratch
and possible key-upgrade behavior. No real wrapped keys, protector records,
credentials or user files were read for these tests.

## Verification

The test extracts the actual changed C++ fragments from the pinned vold
checkout, compiles them against host stubs, and repeats each group using the
pristine `HEAD` implementation as a negative control. It uses synthetic data
only. The optional stub checks invalid dereference rather than invoking
undefined behavior in the original-code control.

| Group | Positive cases | Original-code control |
| --- | --- | --- |
| Default token | 32-byte value matches a zero-padded default token from a nonzero buffer | Partial copy leaves nonzero suffix; rejected |
| Metadata reader | Missing key, existing key, retrieval failure, empty path, explicit provisioning | Missing-key path creates a directory; rejected |
| Keymaster begin | No upgrade, upgrade, read failure, begin failure, scratch-write failure | No-upgrade case dereferences absent optional; rejected |

All **11 host cases and three negative controls** pass. They do not execute
Android services or prove a real key can be unwrapped.

The final incremental `recoveryimage` build exits 0 in **1 minute 22 seconds**.
Recovery/keystore2/helper ELF checks and the three matching Mitee static
closures pass. The existing private/slave mount regression still distinguishes
the implementations correctly. BoardConfig is restored to the canonical
non-crypto profile afterward; generated `out` remains a crypto probe.

Final probe Recovery SHA256:
`2c3f0d3c5973c6b7c65604ec1c88824705159252008b86549202943b6ce83f05`.
The old V5 image is preserved separately. The ordinary raw build image/ZIP is
not an adapted or runtime-validated image for unattended installation.

## Read-only check on the connected tablet

The tablet is currently in normal Android, `sys.boot_completed=1`; this is
not a running-Recovery test. Gatekeeper, KeyMint, shared-secret and secure-clock
AIDL services are registered, and the three vendor init service states are
running. SHA256 of tee-supplicant, Mitee KeyMint, Mitee Gatekeeper and
`libapexsupport.so` matches the local matching-stock extraction exactly.
The existing recovery/KernelSU partition hashes also match the earlier
checkpoint. No files were pushed, no services started/replaced, and the tablet
was not rebooted or flashed during this follow-up.

For the reported no-lock-screen case, the pinned `Password == "!"` synthetic
password branch skips hardware Gatekeeper verification. HIDL-versus-AIDL
Gatekeeper compatibility remains relevant to credential-based unlock, but is
not by itself the blocker for that no-credential branch. Mitee startup, correct
properties, existing metadata mapping, file-key unlock and keystore/SP
compatibility still require actual integration and Recovery testing.

## Reproduce

Prerequisites: existing WSL checkout, matching stock extraction and earlier
display/input/MTP patches. Recovery HEAD is
`6bd902d14f754ab98a7cccc5598f7b9d135cfc38`; vold HEAD is
`a164ba05c5fef288059774a776b2e6e1119957cf`.

```sh
bash diagnostics/build-crypto-probe.sh --result /path/to/new/probe-directory
python3 diagnostics/verify-crypto-probe.py \
  --probe /path/to/new/probe-directory \
  --stock-root /root/orangefox-violin-20261103/stock-thp-305 \
  --ndk /mnt/e/workspace/projects/xiaomi-root/ndk \
  --output /path/to/new/verification-directory
```

The build script applies or verifies these three narrowly scoped patches,
runs the source regressions, records `vold.diff`, builds and captures the root.
It refuses previous build evidence. It has no ADB/fastboot or tablet operation.
The tests can also run separately:

```sh
python3 diagnostics/test-crypto-unlock.py \
  --vold-source /root/orangefox-violin-20261103/source/system/vold \
  --output /path/to/new/test-directory
```

Keep tablet user artifacts under real internal storage's
`Download/OrangeFox-violin`; no new artifacts were placed on the tablet here.

## Source reference

- [Android 16 SyntheticPasswordManager](https://github.com/aosp-mirror/platform_frameworks_base/blob/android16-release/services/core/java/com/android/server/locksettings/SyntheticPasswordManager.java):
  `stretchLskf()` uses `Arrays.copyOf` with `STRETCHED_LSKF_LENGTH=32` for
  the no-password-data case; existing password data uses scrypt.
- [Earlier offline prerequisites and boundaries](CRYPTO-PROBE.md).
