# Skyward-inspired touch candidate for OS3.0.305

The V2 image below is an **unbooted diagnostic candidate**. On reconnection,
the full HAL and input library were tested in the installed OrangeFox's RAM.
Physical touch and position were confirmed by the user after the missing VINTF
base manifest was added. This runtime result does not establish cold startup
of a newly packaged image. No recovery partition was flashed during that test.

The user-supplied Skyward image targets OS4.0.0.14. Only its touch-service
approach and author-reported orientation were used. Its recovery executable,
kernel/module naming, boot header, and rollback settings were not transplanted.
All proprietary files in this candidate come from the matching OS3.0.305 stock
firmware and remain local.

## Changes

- Replace the diagnostic `touch_report_debug` init trigger with the complete
  `vendor.xiaomi.hw.touchfeature-service`, running in the foreground as root.
  Start a dedicated Binder servicemanager first. Do not run both frame consumers.
- Keep the existing kernel/modules, touch firmware, INI, and four models. Add
  seven vendor dependency libraries and four stock touch configuration files.
- Give only the full HAL process a private OS3 `libc++.so`. Static checking found
  eight imports in the service missing from the old Recovery C++ runtime,
  including `__libcpp_verbose_abort` and file-stream functions. The stock runtime
  supplies them; the global Recovery C++ library is unchanged.
- Add a minimal AIDL V1 declaration. The original stock manifest version 8.0 is
  rejected by this build's `assemble_vintf`; the adapted declaration is accepted.
  Also include `/vendor/etc/vintf/manifest.xml`: the older libvintf does not
  discover the ODM fragment without a device base manifest. V2 omitted this
  base and its full HAL aborted when Binder registration was rejected.
- Apply the Skyward author's reported XY swap and screen-Y mirror in
  `libminuitwrp`. The existing source macros had no build wiring in this pinned
  checkout; the dedicated patch adds both compiler flags. Correct the mirror
  boundary from `height - y` to `height - 1 - y` to keep corner taps in bounds.
- Initialize raw mode at most once per boot, skipping the write when it already
  reads `1`. This sysfs operation can reload touch firmware, so it is not polled.
  The launcher refuses mounted data/vendor/odm/persist and uses RAM scratch only.

The orientation patch is specific to the dedicated violin checkout. It is not
a generic change suitable for every OrangeFox device. Physical orientation on
this OS3 tablet was confirmed in the RAM test below; the packaged image still
needs its own cold-start acceptance.

## Local build and packaging

Run in the existing WSL environment. The initial source setup, display patch,
and local THP diagnostic from the earlier work are prerequisites.

```sh
cd /mnt/e/workspace/projects/xiaomi-root/analysis_outputs/orangefox-violin-actions
bash diagnostics/build-skyward-input.sh
python3 diagnostics/prepare-touchfeature-candidate.py \
  --base /mnt/e/workspace/projects/xiaomi-root/outputs/orangefox-violin-20261103/FOX-THP-DIAGNOSTIC-NOT-FOR-FLASH/recovery.img \
  --stock-root /root/orangefox-violin-20261103/stock-thp-305 \
  --input-library /root/orangefox-violin-20261103/source/out/target/product/violin/system/lib64/libminuitwrp.so \
  --avbtool /root/orangefox-violin-20261103/source/external/avb/avbtool.py \
  --output /path/to/a/new/local-output-directory
```

The build logs to `/root/orangefox-violin-20261103/build-skyward-input.log`.
The packer rejects a wrong base image, library, or stock version before creating
its output directory. Exact input hashes are deliberately pinned; changing the
source or build environment requires reviewing and updating the library pin.
No script above uses ADB, fastboot, or any device-flashing command.

## Verified offline result, 2026-11-04

Candidate directory: `FOX-SKYWARD-TOUCHFEATURE-V2-20261104-NOT-FOR-FLASH`, under
the local project's `outputs/orangefox-violin-20261103` directory.

| Item | Result |
| --- | --- |
| Input library build | Exit 0; incremental build reported 45 seconds |
| Library SHA256 | `2aa5b3534b8fc19f82cbe87e7bbae685aa0cb251643a7daef3c345082c7d05f9` |
| Candidate SHA256 | `161aac26299af72298c266e813a1b9c01c81e13e8f2bb256d02307385acf05ae` |
| Image layout | 100 MiB, boot v4, no kernel or boot signature, legacy LZ4 |
| Existing cpio entries changed | Only init.rc and libminuitwrp.so relative to the THP base |
| Runtime manifest | 33/33 hashes checked against the final archive |
| Static ELF closure and strong/versioned exports | Full service, five THP libraries, input library, servicemanager: 8/8 pass |
| Actual C++ mapping | Four corners and center pass; original mirror boundary rejected |
| Init services | New service/trigger syntax accepted by host_init_verifier |
| VINTF declaration | Adapted declaration accepted; original stock version 8.0 rejected |
| Invalid inputs | Wrong base, library and OS4 stock version rejected without output |
| AVB selfcheck | NONE footer/hash passes, rollback index 1788220800/location 11 |

ELF export presence is a static check, not proof of Android linker namespaces,
C++ ABI semantics, successful dlopen, or available sensors/Binder services.
The NONE footer is unsigned and does not prove boot-chain acceptance.

## Live runtime verification, 2026-11-04

Reference: [Skyward PR #1](https://github.com/kirklin/skyward/pull/1), inspected
at head `97b8bd36e669a8ae72ec8ff64ea0b8c486f33e3f`. Its root touch service,
service-description setup and axis reversal informed this adaptation; its
Qualcomm-specific device and secure-stack configuration was not transplanted.

The installed recovery was still the earlier single-plane image. Matching OS3
HAL files and dependencies were staged in RAM, leaving the running GUI's input
library intact for the first comparison. The full HAL exited with signal 6
after `Check failed: status == STATUS_OK`. Tracing servicemanager showed that
both device base manifests were absent, so the valid ODM touch fragment was
never loaded and registration was refused. Adding only the empty device base
manifest and restarting the manually launched Binder manager made it load the
fragment and accept the touch interface. The full HAL then stayed running.

Physical contact produced more than 2,000 event3 lines with the old library,
but the user still could not operate the GUI. Reloading only the GUI with the
compiled XY-swap/Y-mirror library made page changes work; the user confirmed
that touch and position were normal. The boot ID stayed unchanged and all
three recovery_a/recovery_b/init_boot_a hashes retained their earlier values.
GUI startup restarted adbd and killed daemons inherited from its old cgroup;
the manually launched Binder manager and HAL had to be restarted after the GUI.
They were subsequently moved out of adbd's cgroup and survived three MTP cycles.
Init-managed services in a packaged image still need a cold-boot test. See
[Chinese UI and MTP verification](CHINESE-MTP.md) for the newer candidate.

The two missing optional models (`glove_model.tflite`, `FpNonlive.tflite`) were
logged while physical touch worked; they are not fabricated or replaced.
No standalone debug THP consumer ran alongside the full HAL. Device serials,
firmware, models and full runtime traces remain local.

## Pending image acceptance

On reconnection, first identify the current boot and preserve the working
OrangeFox/ADB session. Inspect the existing debug daemon before attempting any
service handover. The new service must demonstrate actual Binder registration,
THP frame processing and event3 point reports in response to physical contact.
Then verify physical corner/center taps and Menu/Files changes after cold boot.
The old synthetic
tab helper uses the old mapping and must not be reused unchanged with this
candidate.

Automatic service startup in the updated image, explicit four-corner coverage,
pens, userdata decryption and stability have not passed device acceptance. The known
kernel `tp_raw` bounds warning (5192-byte write into a 5176-byte field) is still
unfixed. Complete device logs, firmware, models and images are not published.
