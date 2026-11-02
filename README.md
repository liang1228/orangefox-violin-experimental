# Experimental OrangeFox build for Xiaomi Pad 7S Pro (violin)

This private GitHub Actions build adapts the workflow from
https://github.com/LimeBlogs/OrangeFox-Recovery-Builder and uses the local
device tree derived from OS3.0.305.0.WOTCNXM. The workflow builds the 12.1
branch and retains its outputs as private Actions artifacts, not releases.

**Research only: do not flash.** The existing TWRP build did not get past the
Mi logo during a device test. OrangeFox output, hardware support, A/B support,
and userdata decryption have not been tested and are not guaranteed.

The device tree does not include a userdata mount, and the OrangeFox options
here do not constitute encryption support. Kernel module loading, Android
version compatibility, graphics, touch and USB all need independent work.
