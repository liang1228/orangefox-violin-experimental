"""Build an offline-only THP diagnostic from the verified single-plane image.

Run under Linux with lz4 and AOSP avbtool. No device commands are issued.
Stock proprietary files are supplied locally and are not part of this repo.
"""
import argparse
import hashlib
import json
import stat
import struct
import subprocess
from pathlib import Path

BASE_SHA = "69dfbc373757db97bc4bae7b4ba23977d2e6a0e6d52fda0d92796d9d96b7f78c"
FW_SHA = "3effd0693bcd0277940e1b468b98feebffc2e03501d06eb26902d9fd1831185c"
INIT_RC = "system/etc/init/hw/init.rc"
SERVICE = b"""
# Offline diagnostic: modules/firmware/THP only; physical touch not accepted.
service violin-thp /system/bin/sh /system/bin/start-violin-thp.sh
    disabled
    oneshot
    user root
    group root input
    stdio_to_kmsg

on property:init.svc.recovery=running
    start violin-thp
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse(data):
    pos, items = 0, {}
    while True:
        hdr = data[pos:pos + 110]
        if len(hdr) != 110 or hdr[:6] != b"070701":
            raise ValueError("Invalid newc archive")
        fields = [int(hdr[i:i + 8], 16) for i in range(6, 110, 8)]
        begin = pos + 110
        raw_name = data[begin:begin + fields[11]]
        if not raw_name.endswith(b"\0"):
            raise ValueError("Invalid cpio name")
        name = raw_name[:-1].decode()
        start = (begin + fields[11] + 3) & ~3
        end = (start + fields[6] + 3) & ~3
        if end > len(data) or name in items:
            raise ValueError("Truncated archive or duplicate name")
        items[name] = (fields, data[start:start + fields[6]], data[pos:end])
        pos = end
        if name == "TRAILER!!!":
            return items


def entry(name, fields, content):
    fields = fields.copy()
    raw_name = name.encode() + b"\0"
    fields[6], fields[11] = len(content), len(raw_name)
    part = b"070701" + b"".join(f"{v:08x}".encode() for v in fields) + raw_name
    part += b"\0" * (-len(part) % 4)
    return part + content + b"\0" * (-len(content) % 4)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True, type=Path)
    ap.add_argument("--stock-odm", required=True, type=Path)
    ap.add_argument("--avbtool", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    image_data = args.base.read_bytes()
    if sha(image_data) != BASE_SHA or image_data[:8] != b"ANDROID!":
        raise SystemExit("Unexpected base image; no output created")
    if (struct.unpack_from("<I", image_data, 8)[0],
        struct.unpack_from("<I", image_data, 40)[0],
        struct.unpack_from("<I", image_data, 1580)[0]) != (0, 4, 0):
        raise SystemExit("Unexpected boot image layout")
    props = (args.stock_odm / "etc/build.prop").read_text()
    if "ro.odm.build.version.incremental=OS3.0.305.0.WOTCNXM" not in props:
        raise SystemExit("Wrong stock firmware version")
    scripts = Path(__file__).resolve().parent
    additions = {}

    def add(target, source, mode=0o644):
        additions[target] = (stat.S_IFREG | mode, source.read_bytes())

    add("system/bin/touch_report_debug", args.stock_odm / "bin/touch_report_debug", 0o755)
    for name in ("libtouchreport.so", "libtouchreport_hal.so", "libtouchreport_alg.so",
                 "libtouchreport_sensor.so", "libtensorflowlite_touch_c.so"):
        add("vendor/odm/lib64/" + name, args.stock_odm / "lib64" / name)
    for name in ("novatek_nt36536_violin_fw_tm00.bin", "novatek_nt36536_violin_fw_tm01.bin",
                 "novatek_nt36536_violin_fw_tm02.bin", "violin_nova_thp_config.ini",
                 "film_model.tflite", "water_check.tflite", "palm_check.tflite", "smooth.tflite"):
        source = args.stock_odm / "firmware" / name
        if name.endswith(".bin") and sha(source.read_bytes()) != FW_SHA:
            raise SystemExit("Unexpected touch firmware")
        add("vendor/odm/firmware/" + name, source)
    for name in ("load-violin-touch.sh", "start-violin-thp.sh"):
        add("system/bin/" + name, scripts / name, 0o755)

    manifest = "".join(f"{sha(data)}  /{name}\n" for name, (_, data) in sorted(additions.items()))
    additions["system/etc/violin-thp.sha256"] = (stat.S_IFREG | 0o644, manifest.encode())
    ramdisk_size = struct.unpack_from("<I", image_data, 12)[0]
    archive = subprocess.run(["lz4", "-dc"], input=image_data[4096:4096 + ramdisk_size],
                             capture_output=True, check=True).stdout
    old = parse(archive)
    if b"service violin-thp" in old[INIT_RC][1] or set(additions) & set(old):
        raise SystemExit("Unexpected existing THP files")
    for name in list(additions):
        for parent in Path(name).parents:
            p = parent.as_posix()
            if p == ".":
                continue
            if p in old:
                if stat.S_IFMT(old[p][0][1]) != stat.S_IFDIR:
                    raise SystemExit("Non-directory parent in base: " + p)
            elif p not in additions:
                additions[p] = (stat.S_IFDIR | 0o755, b"")

    pieces = []
    for name, (fields, content, raw) in old.items():
        if name == "TRAILER!!!":
            continue
        pieces.append(entry(name, fields, content + SERVICE) if name == INIT_RC else raw)
    ino = max(fields[0] for fields, _, _ in old.values()) + 1
    for name, (mode, content) in sorted(additions.items()):
        fields = [ino, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0, 0, 0, 0, 0, 0, 0, 0]
        pieces.append(entry(name, fields, content))
        ino += 1
    pieces.append(old["TRAILER!!!"][2])
    rebuilt = b"".join(pieces)
    rebuilt += b"\0" * (-len(rebuilt) % 512)
    new = parse(rebuilt)
    if set(new) - set(old) != set(additions) or set(old) - set(new):
        raise ValueError("Archive entries changed unexpectedly")
    for name in old:
        if name != INIT_RC and old[name] != new[name]:
            raise ValueError("Base entry changed: " + name)
    if new[INIT_RC][1] != old[INIT_RC][1] + SERVICE:
        raise ValueError("Unexpected init changes")

    args.output.mkdir(parents=True, exist_ok=False)
    raw, packed = args.output / "diagnostic.cpio", args.output / "diagnostic.lz4"
    raw.write_bytes(rebuilt)
    subprocess.run(["lz4", "-l", "-12", str(raw), str(packed)], check=True)
    if subprocess.run(["lz4", "-dc", str(packed)], capture_output=True, check=True).stdout != rebuilt:
        raise ValueError("Ramdisk compression roundtrip failed")
    payload = packed.read_bytes()
    header = bytearray(image_data[:4096])
    struct.pack_into("<I", header, 12, len(payload))
    image = args.output / "recovery.img"
    image.write_bytes(header + payload + b"\0" * (-len(payload) % 4096))
    subprocess.run(["python3", str(args.avbtool), "add_hash_footer", "--image", str(image),
                    "--partition_size", "104857600", "--partition_name", "recovery",
                    "--algorithm", "NONE", "--rollback_index", "1788220800",
                    "--rollback_index_location", "11", "--salt", sha(rebuilt)], check=True)
    verified = subprocess.run(["python3", str(args.avbtool), "verify_image", "--image", str(image)],
                              capture_output=True, text=True, check=True)
    if image.stat().st_size != 104857600:
        raise ValueError("Unexpected final size")
    report = {"base_sha256": BASE_SHA, "image_sha256": sha(image.read_bytes()),
              "image_bytes": image.stat().st_size, "ramdisk_compression_roundtrip": True,
              "all_other_base_entries_unchanged": True, "modified_base_entries": [INIT_RC],
              "added_entries": {n: {"mode": oct(m), "sha256": sha(d), "size": len(d)}
                                for n, (m, d) in sorted(additions.items())},
              "avb_algorithm": "NONE; unsigned", "avbtool_output": verified.stdout.strip(),
              "boot_verified": False, "physical_touch_verified": False,
              "kernel_bounds_warning_fixed": False, "flash_recommended": False}
    (args.output / "offline-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.output / "violin-thp.sha256").write_text(manifest)
    print(json.dumps({k: v for k, v in report.items() if k != "added_entries"}, indent=2))


if __name__ == "__main__":
    main()
