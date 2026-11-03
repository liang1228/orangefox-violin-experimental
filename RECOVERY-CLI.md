# Violin recovery CLI and touch diagnostics

On the tested single-plane diagnostic image (SHA256
`69dfbc373757db97bc4bae7b4ba23977d2e6a0e6d52fda0d92796d9d96b7f78c`),
ADB reported `recovery` and a root shell. The following commands were tested:

```powershell
adb shell twrp help
adb shell twrp version
adb shell "timeout 12 twrp get tw_version"
adb shell "timeout 12 twrp get tw_is_decrypted"
adb shell "timeout 12 twrp console_message CODEX_CLI_PROBE_20261103"
adb pull /tmp/recovery.log
```

`get tw_version` returned `R12.0`. The console marker appeared in the downloaded
recovery log, confirming that the Recovery process handled the request through
its CLI, rather than merely printing the client program's help.

## Touch initialization evidence

The initial recovery listed only power and volume input devices. SPI devices
were absent, even though the required kernel modules existed in `/lib/modules`.
The recovery module load list omitted the three modules below. The expected
`/odm/firmware` target was also absent because vendor/odm were not mounted.

Loading `xr_spi_mmio` created SPI devices including `spi1.0`. After making the
matching system firmware available in the recovery's RAM filesystem, loading
`xiaomi_touch_violin` and `nt36532_tc_touch` registered
`NVTCapacitiveTouchScreen` and both pen inputs. The modules in recovery matched
the working system's SHA256 hashes. The driver logged `Update firmware success!`
and `/proc/nvt_fw_version` returned `fw_ver=23, x_num=60, y_num=40`.
Recovery automatically reloaded and opened the new event devices.

`diagnostics/load-violin-touch.sh` records the checked runtime loading sequence.
It requires root in an already running recovery and the matching firmware files
to be present under `/odm/firmware`. It verifies hashes before loading modules.
It does not supply firmware or persist changes across a reboot. An idempotent
run against the initialized live recovery passed; automated startup in a newly
built image has not been tested. This is an initialization check, not a stability
or physical touch acceptance test.

The live 6.6.118 kernel subsequently reported a real warning in
`nt36xxx.c:3164`: a 5192-byte copy into the 5176-byte `tp_frame->tp_raw` field,
from `nvt_ts_work_func`. Recovery and ADB remained responsive, but this warning
has not been fixed or shown to be harmless. The driver exposes raw THP interfaces
and `enable_touch_raw` reads `1`; a dependency on vendor userspace touch
processing remains an investigation hypothesis. No vendor daemon has been run
in this test. Physical touch response and coordinate mapping remain unverified.

## Synthetic input test

With the user's authorization to simulate touch, events were injected into
`/dev/input/event3` using `sendevent`. `getevent` captured the events and a
bounded strace attachment confirmed that Recovery itself read them. A synthetic
tap on the built-in Unlock button dismissed the non-password screen overlay.
Tapping Menu and then Files switched pages to `advanced` and `filemanagerlist`;
both page changes were recorded in recovery.log and saved screenshots.

`diagnostics/simulate-violin-tab.sh` reproduces those two tab taps on this exact
3200x2136 UI, after the overlay has been dismissed:

```powershell
adb push diagnostics/simulate-violin-tab.sh /tmp/simulate-violin-tab.sh
adb shell sh /tmp/simulate-violin-tab.sh menu
adb shell sh /tmp/simulate-violin-tab.sh files
```

The helper forces both coordinates to change before the final position, because
evdev otherwise suppresses unchanged values between repeated synthetic taps.
It sends the negative tracking ID after zero pressure/major, matching this
minuitwrp release handling. A successful return means injection completed;
check the page or log to establish that the UI reacted.

The portrait theme is stretched to landscape (X scale 2.962963, Y scale 0.6675).
Source inspection finds mixed scaled and unscaled values in its lock gesture:
the gesture uses an X-scaled 300-unit threshold but compares Y against the raw
`center_y = 1600`. This supports a theme-adaptation fault; no corrected-theme
image was tested. For the live test, `lock_btn` was changed from `0` to `1`,
using the built-in Unlock button instead of the swipe. Screen timeout was
temporarily disabled and then restored to 60 seconds. The button workaround is
left in the running recovery's RAM settings.

These synthetic tests prove that the userspace input and UI path can work.
They bypass touch sensing, raw-frame processing, and the physical coordinate
orientation, so they do not establish that a finger tap works.

This diagnostic did not format or modify userdata. `/data` still failed to
mount. The reported `tw_is_decrypted = 0` does not diagnose the encryption
compatibility issue by itself. Backup, install, wipe, format, decrypt, and reboot
CLI commands were not part of this test.

The image was left in `recovery_a`, with ADB accessible. `recovery_b` and
`init_boot_a` retained their pre-test hashes. Original firmware and complete
device logs are kept locally, outside this Git repository.
