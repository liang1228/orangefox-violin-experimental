# Violin crypto service startup integration

The V6 candidate now wires the matching OS3.0.305.0.WOTCNXM Mitee services
into Recovery init. This is an offline-verified startup candidate. It has
**not booted on the tablet**, and does not enable userdata decryption yet.
Only adaptation source and this report are public; stock binaries, trusted
applications, firmware, models, images and device records remain local.

## Startup behavior

`init.violin.crypto.rc` starts a bounded bootstrap at `early-fs`. It verifies
the packaged hashes and matching OS/security properties, then:

1. Retains the early RAM views of `/data`, `/vendor`, `/odm` and
   `/mnt/vendor/persist` before any of them is mounted from disk.
2. Starts one Binder servicemanager and the full touchfeature service as
   independent init services, outside adbd's cgroup. Touch uses a private
   mount namespace and the saved RAM views, including after a service restart.
3. Waits for touch Binder registration, mounts the **real persist partition
   read-write**, checks its existing TEE directories and aligns device access.
4. Starts matching tee-supplicant, KeyMint V3 and AIDL Gatekeeper. It checks
   actual Binder registration/liveness for KeyMint, shared-secret, secure-clock
   and Gatekeeper before starting keystore2.
5. Waits for keystore2 registration, sets
   `sys.orangefox.crypto.services_ready=1` and releases the Recovery GUI.

Failures also release the GUI. A 75-second outer watchdog, followed by a
2-second kill grace, bounds the bootstrap even if a Binder check blocks;
an init stopped trigger covers termination of the shell. The bootstrap must
start before setting its `started` flag so an initially stopped service cannot
prematurely release the GUI. Init manages security-service restarts and clears
the ready flag on restart; it does not automatically repeat the full readiness
sequence afterward.

KeyMint must be available before metadata-encrypted data is mounted, as
described by [AOSP metadata encryption](https://source.android.com/docs/security/features/encryption/metadata).
This candidate leaves the V5 fstab unchanged, **without a `/data` entry**.
It neither requests metadata keys nor mounts userdata. Starting the matching
TEE services can access persistent/secure storage; a future live startup test
is not a read-only operation.

## Packaged compatibility changes

- Uses the earlier compiled crypto Recovery and keystore2, including the
  [three vold fixes](CRYPTO-UNLOCK-FIXES.md), with their actual library closures.
- Keeps differing stock security libraries in a private search path. The
  shared C++ runtime, corrected touch input library, Chinese resources and
  existing MTP adaptation are preserved.
- Includes the matching vendor set of nine signed TA files. The KeyMint UUID
  is present. Gatekeeper's actual TA requests and secure-world compatibility
  still need runtime evidence; no equivalent claim follows from an ELF audit.
- Adjusts the VINTF XML envelope for the pinned older libvintf while retaining
  real AIDL interface versions, including KeyMint V3. Includes the framework
  keystore2 declaration and avoids duplicate servicemanagers.
- Reports stock Android release 16 and system/vendor security patch
  2026-09-01 to the security stack, plus Mitee Gatekeeper selection. These
  property overrides do not turn the older Recovery userspace into Android 16.
- Compiles two ARM64 helpers: persistent early RAM-view capture/restore and a
  bounded Binder registration/liveness checker. Neither calls a key-service
  method. The mount helper refuses late capture from mounted disk paths.

The [Skyward PR](https://github.com/kirklin/skyward/pull/1) informed touch/service
integration; its Qualcomm security stack is not substituted for violin Mitee.

## Verified offline

Final image: 104857600 bytes; compressed ramdisk: 58902443 bytes.
SHA256: `176bcc4cc7ffd72207e277610a0e16b336a65691c5698421aa84c52768dfef33`.
Base V5 SHA256:
`3f3783413ee6115d985e73f5c8f0fd6d5db1ac815ac1937ea483e378f0b3d6d4`.

- Nine shell-controller scenarios pass, covering ordering, registration,
  integrity, property, snapshot and mount failures with GUI fallback.
- Seven C Binder-checker cases pass against host stubs, including delayed,
  missing and dead services; reference counts balance.
- An actual disposable Linux mount-namespace test retains all four RAM views
  after parent overmounts and a child restart. Its unsafe control sees disk;
  late capture and an unmounted fake snapshot are rejected.
- Fourteen packaged ELF dependency/strong-symbol closures pass; both helpers
  are real AArch64 executables. Removing libapexsupport is detected.
- All 39 touch-manifest and 167 service-manifest entries match packaged bytes.
  The combined init verifier passes with 21 unique services and one Binder
  manager. Vendor/framework manifests parse with KeyMint V3 retained; the
  incompatible stock XML envelope is rejected by the negative control.
- Wrong base, crypto build and firmware fail before creating output. LZ4
  roundtrip, unchanged fstab/resources and AVB footer checks pass. AVB uses
  **NONE, unsigned**, rollback index 1788220800/location 11; this does not
  establish bootloader acceptance.

Host stubs establish controller behavior, not Android service functionality.
Existing V5 charger/lpdumpd service declarations still reference absent
executables; those unrelated inherited entries are recorded in the verifier.

## Runtime acceptance still required

No new Android program was executed on the tablet, and it was not rebooted,
flashed or restored during this integration. Cold boot, real Binder/TEE
operations, TA loading, touch across mounting/USB switches, decryption and
internal-storage MTP remain unverified. The original THP kernel size warning
also remains unresolved.

Before wiring existing synthetic-password unlock, review the pinned
`copySqliteDb()` flow: it copies persistent.sqlite into the temporary keystore
directory after keystore2 has already started. SQLite WAL consistency and the
current firmware's keystore migration/compatibility have not been established.
No database or user keys were inspected here. No-password mode still requires
metadata/file-key unlock; credential-based Gatekeeper compatibility is separate.

Tablet user artifacts belong only under the real unlocked internal storage's
`Download/OrangeFox-violin`. No files were placed in a RAM `/sdcard` directory.

## Reproduce

Requires the existing pinned source and matching local stock extraction;
see [crypto build prerequisites](CRYPTO-PROBE.md). Use new output directories.

```sh
bash diagnostics/build-service-helpers.sh "$NDK" "$SOURCE" \
  "$PROBE/compiled-root" "$NEW_HELPERS"
python3 diagnostics/test-service-integration.py --output "$NEW_HOST_TESTS"
python3 diagnostics/prepare-crypto-services.py \
  --base "$V5_IMAGE" --probe "$PROBE" --stock-root "$STOCK" \
  --helper-root "$NEW_HELPERS" --avbtool "$SOURCE/external/avb/avbtool.py" \
  --output "$NEW_CANDIDATE"
python3 diagnostics/verify-crypto-services.py \
  --candidate "$NEW_CANDIDATE" --base "$V5_IMAGE" --stock-root "$STOCK" \
  --source "$SOURCE" --output "$NEW_VERIFICATION"
```

The host mount regression requires Linux root and mount-namespace support.
These commands do not invoke ADB or fastboot. The local candidate is labelled
NOT-FOR-FLASH until the runtime acceptance above is completed.
