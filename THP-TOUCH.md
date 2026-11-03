# Violin THP runtime diagnostic, 2026-11-04

Loading the touch modules and firmware was insufficient: this driver delivers
raw frames to a userspace THP algorithm, which reports processed points back to
the driver. The matching OS3.0.305.0.WOTCNXM stock `touch_report_debug 0` entry
point can run that algorithm in the existing OrangeFox RAM environment without
starting the complete Android touchfeature Binder service.

## Live evidence

- The stock binary, five libraries, INI, four available sensor models and three
  panel firmware files came from the exact local OS3.0.305 stock ODM image.
  Proprietary files and full device logs are not included in this repository.
- Startup loaded the matching INI and algorithm, created ten threads, reached
  `start_main_loop`, and logged `get_base_delta: get base ready`.
- A six-second bounded strace of the script-started daemon observed seven
  successful GET_FRAME_DATA_INDEX ioctl returns. Tracing detached and the
  daemon remained running. This establishes live raw-frame consumption.
- Synthetic Unlock, Menu and Files taps still worked while the daemon was
  running. New screenshots agreed with recovery.log pages `advanced` and
  `filemanagerlist`. This bypasses the physical sensor and THP point detection.
- The boot ID and recovery PID were unchanged. ADB/root remained available;
  recovery_a, recovery_b and init_boot_a hashes were unchanged. No reboot,
  flash, wipe, format or stock recovery restoration was performed.
- `/data`, `/vendor` and `/odm` were unmounted; supplied files and daemon scratch
  paths were on recovery RAM. `/cache` was already mounted and was not a target
  of these diagnostic operations. Screen timeout was restored to 60 seconds.

The public [MiCode touch source at 99a9aff](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/99a9aff00a2856f065954672660bd0fe0ad0a064/xiaomi-modules/touch_driver)
shows the raw-frame interface and UPDATE_REPORT_POINT reporting path. That is
the violin-v-oss release, not a verified exact source match for the running
6.6.118 kernel. It was used to understand the interface, not to replace modules.

## Runtime helper

`diagnostics/start-violin-thp.sh` is a foreground diagnostic entry point. It
requires a running root recovery on violin, refuses mounted data/vendor/odm,
checks the supplied SHA256 manifest, invokes the checked module loader, creates
RAM scratch paths, and execs the stock THP entry point with the ODM library path.
The live helper passed both an already-running check and an actual daemon start.
It does not install files by itself and is not a general Android boot service.

## Offline candidate

`diagnostics/prepare-thp-diagnostic.py` adds those locally supplied files and a
recovery-running init trigger to the verified single-plane diagnostic base.
Run with Linux Python, lz4 and AOSP avbtool; all paths are explicit:

```sh
python3 diagnostics/prepare-thp-diagnostic.py \
  --base /path/to/verified-single-plane/recovery.img \
  --stock-odm /path/to/extracted-OS3.0.305/odm \
  --avbtool /path/to/avbtool.py \
  --output /path/to/new-offline-output
```

The base SHA256 must be
`69dfbc373757db97bc4bae7b4ba23977d2e6a0e6d52fda0d92796d9d96b7f78c`.
The candidate generated locally was 104857600 bytes, SHA256
`f999c75ec39545513e66148ccd437451ad2155ada29dd1202ee0a2020438288e`.
All original cpio entries except the appended init.rc section were unchanged;
ramdisk compression roundtrip and the NONE hash footer self-check passed. A
wrong-base negative check was rejected before an output directory was created.

The candidate was not flashed or booted. NONE is unsigned; this self-check does
not establish a trusted boot chain. The init trigger and cold module/firmware
startup remain untested together in a fresh boot. The live foreground helper
test started after the touch modules and firmware had already been initialized.

## Remaining limits

- Physical fingers, coordinates, orientation and pens remain unverified. No
  UPDATE_REPORT_POINT was observed during the untouched idle trace; this is
  not evidence of successful physical contact detection.
- The 5192-byte copy into the 5176-byte `tp_frame->tp_raw` field still needs a
  fix using matching kernel source and ABI. Do not suppress its bounds check or
  treat the observed warning as harmless.
- Startup logs report missing `libtouchreport_alg_2.so`, `glove_model.tflite`,
  `FpNonlive.tflite` and a vendor INI. Those files were also absent from the
  extracted stock vendor/odm. The observed daemon reached its idle main loop
  despite these messages; all algorithm modes have not been validated.
- Empty-queue GET_FRAME_DATA_INDEX calls return -1 in the inspected driver.
  The resulting strace EPERM text alone is not proof of an SELinux denial.
- The live THP additions are volatile and do not survive reboot. The offline
  candidate is a diagnostic, not a stable release. Data decryption, MTP, backup
  and installation remain outside this test.
