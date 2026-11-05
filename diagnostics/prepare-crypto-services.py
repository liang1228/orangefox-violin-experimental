"""Integrate matching Mitee startup into the verified V5 ramdisk, offline only.

The output keeps encrypted userdata absent from recovery.fstab. It tests service
startup, not key retrieval or decryption. Firmware/TA files stay local.
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
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


cpio = module('prepare-thp-diagnostic')
touch = module('prepare-touchfeature-candidate')
elf = module('check-elf-closure')
BASE_SHA = '3f3783413ee6115d985e73f5c8f0fd6d5db1ac815ac1937ea483e378f0b3d6d4'
RECOVERY_SHA = '2c3f0d3c5973c6b7c65604ec1c88824705159252008b86549202943b6ce83f05'
PROGRAMS = (
    'bin/tee-supplicant',
    'bin/hw/android.hardware.security.keymint@3.0-service.mitee',
    'bin/hw/android.hardware.gatekeeper-service.mitee',
)
MANIFESTS = (
    'android.hardware.security.keymint-service.mitee.xml',
    'android.hardware.security.sharedsecret-service.mitee.xml',
    'android.hardware.security.secureclock-service.mitee.xml',
    'android.hardware.gatekeeper-service.mitee.xml',
)
PROPERTIES = {
    'ro.build.version.release': '16',
    'ro.build.version.security_patch': '2026-09-01',
    'ro.vendor.build.security_patch': '2026-09-01',
    'ro.hardware.gatekeeper': 'mitee',
    'ro.orangefox.crypto_enabled': '1',
    'ro.orangefox.crypto_firmware': 'OS3.0.305.0.WOTCNXM',
}


def checked_audit(program, roots):
    audit = elf.audit(program, roots)
    if audit['missing_libraries'] or audit['unresolved_strong_symbols']:
        raise ValueError('ELF closure failed: ' + json.dumps(audit))
    return audit


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ('base', 'probe', 'stock-root', 'helper-root', 'avbtool', 'output'):
        ap.add_argument('--' + flag, type=Path, required=True)
    args = ap.parse_args()
    image = args.base.read_bytes()
    if cpio.sha(image) != BASE_SHA:
        ap.error('Unexpected V5 base; no output created')
    for relative, prop in (('vendor/build.prop', 'ro.vendor.build.version.incremental'),
                           ('odm/etc/build.prop', 'ro.odm.build.version.incremental')):
        if f'{prop}=OS3.0.305.0.WOTCNXM' not in (args.stock_root / relative).read_text().splitlines():
            ap.error('Wrong stock firmware; no output created')
    compiled = args.probe / 'compiled-root'
    if (args.probe / 'exit-code.txt').read_text().strip() != '0' or cpio.sha(
            (compiled / 'system/bin/recovery').read_bytes()) != RECOVERY_SHA:
        ap.error('Unexpected crypto build; no output created')
    if args.output.exists():
        ap.error('Use a new output directory; previous evidence is preserved')
    size = struct.unpack_from('<I', image, 12)[0]
    old = cpio.parse(subprocess.run(['lz4', '-dc'], input=image[4096:4096+size],
                                    check=True, capture_output=True).stdout)
    changes = {}

    def put(name, data, mode=stat.S_IFREG | 0o644):
        if name in changes and changes[name] != (mode, data):
            raise ValueError('Conflicting replacement: ' + name)
        changes[name] = (mode, data)

    def add(name, source, executable=False):
        put(name, source.read_bytes(), stat.S_IFREG | (0o755 if executable else 0o644))

    # Overlay the actual dependency closures, including the changed vold libs.
    for name in ('recovery', 'keystore2'):
        add('system/bin/' + name, compiled / 'system/bin' / name, True)
        audit = checked_audit(compiled / 'system/bin' / name, [compiled / 'system/lib64'])
        for obj in audit['objects'].values():
            src = Path(obj['path'])
            if src.parent == compiled / 'system/lib64':
                add('system/lib64/' + src.name, src)
    if cpio.sha(changes['system/lib64/libminuitwrp.so'][1]) != touch.INPUT_SHA:
        ap.error('Crypto build lost the verified touch mapping')

    private = 'system/lib64/violin-crypto/'
    roots = [args.stock_root / 'vendor/lib64', args.stock_root / 'odm/lib64',
             args.stock_root / 'system-support-libs', compiled / 'system/lib64']
    for program in PROGRAMS:
        src = args.stock_root / 'vendor' / program
        add('vendor/' + program, src, True)
        for obj in checked_audit(src, roots)['objects'].values():
            path = Path(obj['path'])
            if path != src:
                normal = changes.get('system/lib64/' + path.name)
                # Use the common runtime only when the bytes are identical.
                # Stock-only or different-version libraries stay private.
                if normal is None or normal[1] != path.read_bytes():
                    add(private + path.name, path)
    # Keep the vendor TA set, including the UUID referenced by KeyMint.
    # Xiaomi ODM daemons are outside this startup set. Actual TA requests
    # from the secure world still require runtime verification.
    ta_count = 0
    for src in sorted((args.stock_root / 'vendor/mitee/ta').glob('*.ta')):
        add('vendor/mitee/ta/' + src.name, src)
        ta_count += 1
    if ta_count != 9:
        ap.error('Incomplete matching stock TA set')
    keymint_ta = 'dba51a17-0563-11e7-93b16fa7b0071a51.ta'
    if 'vendor/mitee/ta/' + keymint_ta not in changes:
        ap.error('Referenced KeyMint TA is missing')

    # Change the XML envelope supported by this old libvintf, retaining actual
    # AIDL interface versions (KeyMint V3, not falsely relabelled as V1).
    for name in MANIFESTS:
        tree = ET.parse(args.stock_root / 'vendor/etc/vintf/manifest' / name)
        tree.getroot().set('version', '1.0')
        put('vendor/etc/vintf/manifest/' + name,
            ET.tostring(tree.getroot(), encoding='utf-8') + b'\n')
    put('system/etc/vintf/manifest.xml', b'<manifest version="1.0" type="framework"/>\n')
    add('system/etc/vintf/manifest/android.system.keystore2-service.xml',
        compiled / 'system/etc/vintf/manifest/android.system.keystore2-service.xml')
    keystore_rc = (compiled / 'system/etc/init/keystore2.rc').read_text()
    if keystore_rc.count('on late-init\n    start keystore2\n') != 1:
        raise ValueError('Unexpected keystore startup layout')
    keystore_rc = keystore_rc.replace('on late-init\n    start keystore2\n', '')
    keystore_rc = keystore_rc.replace('service keystore2 /system/bin/keystore2 /tmp/misc/keystore\n',
        'service keystore2 /system/bin/keystore2 /tmp/misc/keystore\n    disabled\n')
    put('system/etc/init/keystore2.rc', keystore_rc.encode())

    rc = old[cpio.INIT_RC][1]
    if rc.count(touch.SERVICE) != 1:
        raise ValueError('Unexpected V5 touch services')
    rc = b'import /init.violin.crypto.rc\n' + rc.replace(touch.SERVICE, b'')
    put(cpio.INIT_RC, rc, old[cpio.INIT_RC][0][1])
    recovery_rc = old['init.recovery.service.rc'][1]
    if recovery_rc.count(b'service recovery /system/bin/recovery\n') != 1:
        raise ValueError('Unexpected GUI service')
    put('init.recovery.service.rc', recovery_rc.replace(
        b'service recovery /system/bin/recovery\n',
        b'service recovery /system/bin/recovery\n    disabled\n'))
    add('init.violin.crypto.rc', HERE / 'violin-crypto.rc')
    for name in ('start-violin-crypto.sh', 'start-violin-touchfeature.sh', 'load-violin-touch.sh'):
        add('system/bin/' + name, HERE / name, True)
    for name in ('violin-touch-mountns', 'violin-service-ready'):
        add('system/bin/' + name, args.helper_root / name, True)

    properties = old['prop.default'][1].decode().splitlines()
    for key, value in PROPERTIES.items():
        matches = [i for i, line in enumerate(properties) if line.startswith(key + '=')]
        if len(matches) > 1:
            raise ValueError('Duplicate property: ' + key)
        if matches:
            properties[matches[0]] = key + '=' + value
        else:
            properties.append(key + '=' + value)
    put('prop.default', ('\n'.join(properties) + '\n').encode())
    # ueventd applies permissions again if a TEE/RPMB node is recreated.
    ueventd = old['system/etc/ueventd.rc'][1]
    ueventd += b'\n# Matching Mitee service devices\n'
    for name in ('tee0', 'teepriv0', 'rpmb0', 'mmcblk0rpmb', '0:0:0:49476', 'ufs-bsg0'):
        ueventd += f'/dev/{name} 0660 system system\n'.encode()
    put('system/etc/ueventd.rc', ueventd)

    # Update the old touch manifest, which includes its launcher and init.rc.
    manifest = {}
    for line in old['system/etc/violin-touchfeature.sha256'][1].decode().splitlines():
        digest, name = line.split('  ', 1)
        if cpio.sha(old[name.lstrip('/')][1]) != digest:
            raise ValueError('V5 manifest mismatch: ' + name)
        manifest[name.lstrip('/')] = digest
    for name in manifest:
        if name in changes:
            manifest[name] = cpio.sha(changes[name][1])
    put('system/etc/violin-touchfeature.sha256', ''.join(
        f'{digest}  /{name}\n' for name, digest in sorted(manifest.items())).encode())
    # Includes every touched regular file, except the self-referential manifest.
    put('system/etc/violin-services.sha256', ''.join(
        f'{cpio.sha(data)}  /{name}\n' for name, (mode, data) in sorted(changes.items())
        if stat.S_ISREG(mode)).encode())
    for name in list(changes) + ['mnt/vendor/persist']:
        targets = [Path(name)] if name == 'mnt/vendor/persist' else []
        targets += list(Path(name).parents)
        for parent in targets:
            p = parent.as_posix()
            if p == '.':
                continue
            if p in old:
                if not stat.S_ISDIR(old[p][0][1]):
                    raise ValueError('Non-directory parent: ' + p)
            elif p not in changes:
                put(p, b'', stat.S_IFDIR | 0o755)

    # Preserve old entries byte-for-byte unless explicitly changed.
    pieces = []
    ino = max(f[0] for f, _, _ in old.values()) + 1
    for name, (fields, data, raw) in old.items():
        if name != 'TRAILER!!!':
            if name in changes:
                fields = fields.copy()
                fields[1] = changes[name][0]
                pieces.append(cpio.entry(name, fields, changes[name][1]))
            else:
                pieces.append(raw)
    for name, (mode, data) in sorted(changes.items()):
        if name not in old:
            fields = [ino, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0, 0, 0, 0, 0, 0, 0, 0]
            pieces.append(cpio.entry(name, fields, data))
            ino += 1
    pieces.append(old['TRAILER!!!'][2])
    archive = b''.join(pieces)
    archive += b'\0' * (-len(archive) % 512)
    new = cpio.parse(archive)
    assert set(new) == set(old) | set(changes)
    for name in old:
        if name not in changes:
            assert new[name] == old[name], name
    for name, (mode, data) in changes.items():
        assert new[name][0][1] == mode and new[name][1] == data, name
    assert new['system/etc/recovery.fstab'] == old['system/etc/recovery.fstab']
    args.output.mkdir(parents=True, exist_ok=False)
    raw, packed = args.output / 'candidate.cpio', args.output / 'candidate.lz4'
    raw.write_bytes(archive)
    subprocess.run(['lz4', '-l', '-12', str(raw), str(packed)], check=True)
    payload = packed.read_bytes()
    assert subprocess.run(['lz4', '-dc', str(packed)], capture_output=True,
                          check=True).stdout == archive
    header = bytearray(image[:4096])
    struct.pack_into('<I', header, 12, len(payload))
    final = args.output / 'recovery.img'
    final.write_bytes(header + payload + b'\0' * (-len(payload) % 4096))
    subprocess.run(['python3', str(args.avbtool), 'add_hash_footer', '--image', str(final),
        '--partition_size', '104857600', '--partition_name', 'recovery', '--algorithm', 'NONE',
        '--rollback_index', '1788220800', '--rollback_index_location', '11', '--salt',
        cpio.sha(archive)], check=True)
    avb = subprocess.run(['python3', str(args.avbtool), 'verify_image', '--image', str(final)],
                         check=True, capture_output=True, text=True)
    report = dict(base_sha256=BASE_SHA, image_sha256=cpio.sha(final.read_bytes()),
        image_bytes=final.stat().st_size, recovery_sha256=RECOVERY_SHA,
        changed_files={name: dict(mode=oct(mode), sha256=cpio.sha(data), size=len(data))
                       for name, (mode, data) in sorted(changes.items())},
        ta_files=ta_count, property_overrides=PROPERTIES, avb_output=avb.stdout,
        ramdisk_roundtrip=True, userdata_fstab_unchanged=True, tablet_flashed=False,
        boot_verified=False, services_device_verified=False, decryption_verified=False,
        flash_recommended=False)
    (args.output / 'integration.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'changed_files'}, indent=2))


if __name__ == '__main__':
    main()
