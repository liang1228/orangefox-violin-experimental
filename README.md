# Experimental OrangeFox build for Xiaomi Pad 7S Pro (violin)

This public GitHub Actions experiment adapts the workflow from
https://github.com/LimeBlogs/OrangeFox-Recovery-Builder and uses the local
device tree derived from OS3.0.305.0.WOTCNXM. The workflow builds the 12.1
branch and retains its build outputs as Actions artifacts, not stable releases.

## Latest diagnostic status (2026-11-04)

The single-plane diagnostic booted with working graphics and root ADB. Matching
stock THP files were loaded into the running recovery RAM; the daemon reached
its algorithm loop and consumed raw touch frames. Synthetic UI taps worked, but
physical touch is still reported unresponsive and has not passed acceptance.
The kernel touch buffer bounds warning also remains unresolved.

The newer THP image has only passed offline checks and has not been booted.
See [THP diagnostics](THP-TOUCH.md), [CLI evidence](RECOVERY-CLI.md), and
[local build instructions](LOCAL-BUILD.md). Proprietary stock runtime files and
full device logs are kept outside this repository.

## Initial experiment (historical)

**Research only: do not flash.** The existing TWRP build did not get past the
Mi logo during a device test. OrangeFox output, hardware support, A/B support,
and userdata decryption have not been tested and are not guaranteed.

The device tree does not include a userdata mount, and the OrangeFox options
here do not constitute encryption support. Kernel module loading, Android
version compatibility, graphics, touch and USB all need independent work.
