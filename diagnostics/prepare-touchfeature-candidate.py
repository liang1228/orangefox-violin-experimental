"""Adapt the local OS3 THP diagnostic using Skyward's touch-service approach.

No image from OS4 is flashed or executed. No device commands are issued.
Only this exact OS3 base and locally compiled input library are accepted.
"""
import argparse
import importlib.util
import json
import stat
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


cpio = module("prepare-thp-diagnostic")
elf = module("check-elf-closure")
BASE_SHA = "f999c75ec39545513e66148ccd437451ad2155ada29dd1202ee0a2020438288e"
INPUT_SHA = "2aa5b3534b8fc19f82cbe87e7bbae685aa0cb251643a7daef3c345082c7d05f9"
EXTRA_LIBS = (
    "libmisight.so", "libxml2.so", "vendor.xiaomi.hw.touchfeature-V1-ndk.so",
    "android.frameworks.sensorservice-V1-ndk.so", "android.hardware.sensors-V2-ndk.so",
    "android.hardware.common-V2-ndk.so", "android.hardware.common.fmq-V1-ndk.so",
)
SERVICE = b"""
# Skyward-inspired OS3 diagnostic. Do not also start touch_report_debug.
service violin-servicemanager /system/bin/servicemanager
    disabled
    oneshot
    user root
    group root readproc
    seclabel u:r:recovery:s0
    stdio_to_kmsg

service violin-touchfeature /system/bin/sh /system/bin/start-violin-touchfeature.sh
    disabled
    oneshot
    user root
    group root input
    seclabel u:r:recovery:s0
    stdio_to_kmsg

on property:init.svc.recovery=running
    start violin-servicemanager

on property:init.svc.violin-servicemanager=running && property:init.svc.recovery=running
    start violin-touchfeature
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--stock-root", type=Path, required=True)
    ap.add_argument("--input-library", type=Path, required=True)
    ap.add_argument("--avbtool", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    image = args.base.read_bytes()
    if cpio.sha(image) != BASE_SHA:
        raise SystemExit("Unexpected THP base; no output created")
    if cpio.sha(args.input_library.read_bytes()) != INPUT_SHA:
        raise SystemExit("Unexpected input library; no output created")
    props = (args.stock_root / "odm/etc/build.prop").read_text()
    if "ro.odm.build.version.incremental=OS3.0.305.0.WOTCNXM" not in props:
        raise SystemExit("Wrong stock version")
    if image[:8] != b"ANDROID!" or tuple(struct.unpack_from("<I", image, o)[0]
                                       for o in (8, 40, 1580)) != (0, 4, 0):
        raise SystemExit("Unexpected boot layout")
    size = struct.unpack_from("<I", image, 12)[0]
    archive = subprocess.run(["lz4", "-dc"], input=image[4096:4096 + size],
                             capture_output=True, check=True).stdout
    old = cpio.parse(archive)
    rc = old[cpio.INIT_RC][1]
    if rc.count(cpio.SERVICE) != 1 or b"service violin-touchfeature" in rc:
        raise SystemExit("Unexpected init service layout")
    for name, (_, content, _) in old.items():
        if name.endswith(".rc") and b"service servicemanager " in content:
            raise SystemExit("Unexpected existing Binder service")
    changes = {}

    def add(name, path, mode=0o644):
        changes[name] = (stat.S_IFREG | mode, path.read_bytes())

    add("system/bin/vendor.xiaomi.hw.touchfeature-service",
        args.stock_root / "odm/bin/hw/vendor.xiaomi.hw.touchfeature-service", 0o755)
    stock_manifest = ET.parse(args.stock_root / "odm/etc/vintf/manifest/vendor.xiaomi.hw.touchfeature-service.xml")
    hal = stock_manifest.getroot().find("hal")
    if (hal is None or hal.get("format") != "aidl" or
            hal.findtext("name") != "vendor.xiaomi.hw.touchfeature" or
            hal.findtext("fqname") != "ITouchFeature/default"):
        raise SystemExit("Unexpected stock touchfeature interface")
    add("vendor/odm/etc/vintf/manifest/vendor.xiaomi.hw.touchfeature-service.xml",
        HERE / "violin-touchfeature-manifest.xml")
    for name in ("Pencil_Posture.xml", "gameturbotool-fastinput.json",
                 "gameturbotool.json", "stylus_game_config.json"):
        add("vendor/odm/etc/touch/" + name, args.stock_root / "odm/etc/touch" / name)
    for name in EXTRA_LIBS:
        add("vendor/odm/lib64/" + name, args.stock_root / "vendor/lib64" / name)
    add("vendor/odm/lib64/touchfeature/libc++.so", args.stock_root / "vendor/lib64/libc++.so")
    add("system/bin/start-violin-touchfeature.sh", HERE / "start-violin-touchfeature.sh", 0o755)
    add("system/lib64/libminuitwrp.so", args.input_library)
    changes[cpio.INIT_RC] = (old[cpio.INIT_RC][0][1], rc.replace(cpio.SERVICE, SERVICE))
    manifest_items = {}
    for line in old["system/etc/violin-thp.sha256"][1].decode().splitlines():
        digest, name = line.split("  ", 1)
        if cpio.sha(old[name.lstrip("/")][1]) != digest:
            raise ValueError("Old THP manifest mismatch: " + name)
        manifest_items[name] = digest
    for name, (_, content) in changes.items():
        manifest_items["/" + name] = cpio.sha(content)
    manifest = "".join(f"{digest}  {name}\n" for name, digest in sorted(manifest_items.items()))
    changes["system/etc/violin-touchfeature.sha256"] = (stat.S_IFREG | 0o644, manifest.encode())

    for name in list(changes):
        for parent in Path(name).parents:
            p = parent.as_posix()
            if p == ".":
                continue
            if p in old:
                if not stat.S_ISDIR(old[p][0][1]):
                    raise ValueError("Non-directory parent: " + p)
            elif p not in changes:
                changes[p] = (stat.S_IFDIR | 0o755, b"")
    pieces, ino = [], max(f[0] for f, _, _ in old.values()) + 1
    for name, (fields, content, raw) in old.items():
        if name == "TRAILER!!!":
            continue
        pieces.append(cpio.entry(name, fields, changes[name][1]) if name in changes else raw)
    for name, (mode, content) in sorted(changes.items()):
        if name not in old:
            fields = [ino, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0, 0, 0, 0, 0, 0, 0, 0]
            pieces.append(cpio.entry(name, fields, content))
            ino += 1
    pieces.append(old["TRAILER!!!"][2])
    rebuilt = b"".join(pieces)
    rebuilt += b"\0" * (-len(rebuilt) % 512)
    new = cpio.parse(rebuilt)
    if set(new) != set(old) | set(changes):
        raise ValueError("Unexpected archive entries")
    for name in old:
        if name not in changes and new[name] != old[name]:
            raise ValueError("Unexpected base change: " + name)
    for name, (mode, data) in changes.items():
        if new[name][0][1] != mode or new[name][1] != data:
            raise ValueError("Incorrect replacement: " + name)

    # Audit the actual packaged files, including THP libraries loaded via dlopen.
    with tempfile.TemporaryDirectory(prefix="violin-elf-") as tmp:
        root = Path(tmp)
        for name, (fields, data, _) in new.items():
            if stat.S_ISREG(fields[1]) and data[:4] == b"\x7fELF":
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        normal = [root / p for p in ("system/lib64", "vendor/lib64", "vendor/odm/lib64")]
        private = [root / "vendor/odm/lib64/touchfeature"] + normal
        targets = ["system/bin/vendor.xiaomi.hw.touchfeature-service"]
        targets += ["vendor/odm/lib64/" + n for n in (
            "libtouchreport.so", "libtouchreport_hal.so", "libtouchreport_alg.so",
            "libtouchreport_sensor.so", "libtensorflowlite_touch_c.so")]
        audits = [elf.audit(root / n, private) for n in targets]
        audits += [elf.audit(root / n, normal) for n in (
            "system/lib64/libminuitwrp.so", "system/bin/servicemanager")]
        for item in audits:
            if item["missing_libraries"] or item["unresolved_strong_symbols"]:
                raise ValueError("ELF audit failed: " + json.dumps(item))
            # Temporary extraction paths are not useful to the report reader.
            item["program"] = "/" + str(Path(item["program"]).relative_to(root))
            for obj in item["objects"].values():
                obj["path"] = "/" + str(Path(obj["path"]).relative_to(root))

    args.output.mkdir(parents=True, exist_ok=False)
    raw, packed = args.output / "candidate.cpio", args.output / "candidate.lz4"
    raw.write_bytes(rebuilt)
    subprocess.run(["lz4", "-l", "-12", str(raw), str(packed)], check=True)
    if subprocess.run(["lz4", "-dc", str(packed)], check=True, capture_output=True).stdout != rebuilt:
        raise ValueError("Compression roundtrip failed")
    payload = packed.read_bytes()
    header = bytearray(image[:4096])
    struct.pack_into("<I", header, 12, len(payload))
    final = args.output / "recovery.img"
    final.write_bytes(header + payload + b"\0" * (-len(payload) % 4096))
    subprocess.run(["python3", str(args.avbtool), "add_hash_footer", "--image", str(final),
                    "--partition_size", "104857600", "--partition_name", "recovery",
                    "--algorithm", "NONE", "--rollback_index", "1788220800",
                    "--rollback_index_location", "11", "--salt", cpio.sha(rebuilt)], check=True)
    verified = subprocess.run(["python3", str(args.avbtool), "verify_image", "--image", str(final)],
                              check=True, capture_output=True, text=True)
    if final.stat().st_size != 104857600:
        raise ValueError("Unexpected partition size")
    report = {"base_sha256": BASE_SHA, "image_sha256": cpio.sha(final.read_bytes()),
              "image_bytes": final.stat().st_size, "input_library_sha256": INPUT_SHA,
              "input_mapping": "swap XY, mirror screen Y; author-derived, not physical acceptance",
              "ramdisk_compression_roundtrip": True, "all_other_base_entries_unchanged": True,
              "changes": {n: {"sha256": cpio.sha(d), "mode": oct(m), "size": len(d)}
                          for n, (m, d) in sorted(changes.items())},
              "manifest_files": len(manifest_items), "static_elf_audits": audits,
              "avb_algorithm": "NONE; unsigned", "rollback_index": 1788220800,
              "rollback_index_location": 11, "avbtool_output": verified.stdout.strip(),
              "boot_verified": False, "binder_registration_verified": False,
              "physical_touch_verified": False, "kernel_bounds_warning_fixed": False,
              "flash_recommended": False}
    (args.output / "offline-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.output / "violin-touchfeature.sha256").write_text(manifest)
    print(json.dumps({k: v for k, v in report.items() if k not in ("changes", "static_elf_audits")}, indent=2))


if __name__ == "__main__":
    main()
