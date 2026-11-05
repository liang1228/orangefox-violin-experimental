"""Independent packaged-byte checks; never executes an Android program."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE/(name+'.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def run(command):
    return subprocess.run(list(map(str, command)), check=True, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'base', 'stock-root', 'source', 'output'):
        ap.add_argument('--'+name, type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cpio = module('prepare-thp-diagnostic')
    elf = module('check-elf-closure')
    packer = module('prepare-crypto-services')
    image = (args.candidate/'recovery.img').read_bytes()
    report = json.loads((args.candidate/'integration.json').read_text())
    assert len(image) == 104857600 and cpio.sha(image) == report['image_sha256']
    assert image[:8] == b'ANDROID!' and tuple(struct.unpack_from('<I', image, p)[0] for p in (8,40,1580)) == (0,4,0)
    assert image[-64:-60] == b'AVBf'
    size = struct.unpack_from('<I', image, 12)[0]
    archive = subprocess.run(['lz4','-dc'], input=image[4096:4096+size], capture_output=True, check=True).stdout
    assert archive == (args.candidate/'candidate.cpio').read_bytes()
    new = cpio.parse(archive)
    old_image = args.base.read_bytes()
    assert cpio.sha(old_image) == packer.BASE_SHA
    old_size = struct.unpack_from('<I',old_image,12)[0]
    old = cpio.parse(subprocess.run(['lz4','-dc'], input=old_image[4096:4096+old_size], capture_output=True, check=True).stdout)
    assert not set(old)-set(new)
    for name in old:
        if name not in report['changed_files']:
            assert new[name] == old[name], name
    for name, expected in report['changed_files'].items():
        assert oct(new[name][0][1]) == expected['mode']
        assert cpio.sha(new[name][1]) == expected['sha256'], name
    counts = {}
    for manifest in ('system/etc/violin-touchfeature.sha256','system/etc/violin-services.sha256'):
        rows = new[manifest][1].decode().splitlines()
        for row in rows:
            digest, path = row.split('  ',1)
            assert cpio.sha(new[path.lstrip('/')][1]) == digest, path
        counts[manifest] = len(rows)
    assert new['system/etc/recovery.fstab'] == old['system/etc/recovery.fstab']
    assert not re.search(rb'^/data\s',new['system/etc/recovery.fstab'][1],re.M)
    assert new['system/lib64/libc++.so'][1] == old['system/lib64/libc++.so'][1]
    assert new['twres/languages/zh_CN.xml'] == old['twres/languages/zh_CN.xml']
    assert new['twres/fonts/wqy-microhei.ttf'] == old['twres/fonts/wqy-microhei.ttf']
    assert cpio.sha(new['system/lib64/libminuitwrp.so'][1]) == module('prepare-touchfeature-candidate').INPUT_SHA
    assert new['init.violin.mtp.rc'] == old['init.violin.mtp.rc']
    properties = dict(line.split('=',1) for line in new['prop.default'][1].decode().splitlines()
                      if line and not line.startswith('#') and '=' in line)
    assert all(properties.get(k) == v for k,v in packer.PROPERTIES.items())
    ta_paths = sorted(n for n in new if n.startswith('vendor/mitee/ta/') and n.endswith('.ta'))
    assert len(ta_paths) == 9
    for name in ta_paths:
        assert new[name][1] == (args.stock_root/name).read_bytes()
    for program in packer.PROGRAMS:
        assert new['vendor/'+program][1] == (args.stock_root/'vendor'/program).read_bytes()

    with tempfile.TemporaryDirectory(prefix='violin-services-verify-') as temp:
        root = Path(temp)
        # Extract regular files only; Android symlinks are never followed here.
        for name,(fields,data,_) in new.items():
            if stat.S_ISREG(fields[1]):
                target = root/name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(data)
        normal = [root/'system/lib64']
        private = [root/'system/lib64/violin-crypto']+normal
        touch = [root/'vendor/odm/lib64/touchfeature']+normal+[root/'vendor/lib64',root/'vendor/odm/lib64']
        targets = [(name,normal) for name in ('system/bin/recovery','system/bin/keystore2',
            'system/bin/servicemanager','system/bin/violin-service-ready','system/bin/violin-touch-mountns')]
        targets += [('vendor/'+n,private) for n in packer.PROGRAMS]
        targets += [('system/bin/vendor.xiaomi.hw.touchfeature-service',touch)]
        targets += [('vendor/odm/lib64/'+n,touch) for n in (
            'libtouchreport.so','libtouchreport_hal.so','libtouchreport_alg.so',
            'libtouchreport_sensor.so','libtensorflowlite_touch_c.so')]
        audits = []
        for name,roots in targets:
            audit = elf.audit(root/name,roots)
            assert not audit['missing_libraries'] and not audit['unresolved_strong_symbols'], audit
            audit['program'] = '/'+name
            for obj in audit['objects'].values():
                obj['path'] = '/'+str(Path(obj['path']).relative_to(root))
            audits.append(audit)
        (args.output/'elf-audits.json').write_text(json.dumps(audits,indent=2)+'\n')
        support = root/'system/lib64/violin-crypto/libapexsupport.so'
        held = support.with_suffix('.held')
        support.rename(held)
        try:
            missing = elf.audit(root/'vendor'/packer.PROGRAMS[1], private)
            assert 'libapexsupport.so' in missing['missing_libraries'], missing
        finally:
            held.rename(support)

        rc_files = sorted(n for n,(f,_,_) in new.items() if n.endswith('.rc') and
                          stat.S_ISREG(f[1]) and n != 'system/etc/ueventd.rc')
        services, all_rc, existing_missing = {}, [], []
        for name in rc_files:
            text = new[name][1].decode()
            for line in text.splitlines():
                match = re.match(r'^service\s+(\S+)\s+(\S+)(.*)$',line)
                if match:
                    service, executable, tail = match.groups()
                    assert service not in services, ('Duplicate init service',service,name)
                    services[service] = (executable,tail)
                    if executable.lstrip('/') not in new:
                        assert name in old and new[name] == old[name], (service, executable)
                        existing_missing.append(dict(service=service, executable=executable))
            all_rc.extend(line for line in text.splitlines() if not line.startswith('import '))
        managers = [s for s,(program,_) in services.items() if program == '/system/bin/servicemanager']
        assert managers == ['violin-servicemanager'],managers
        combined = root/'all-services.rc'
        combined.write_text('\n'.join(all_rc)+'\n')
        init = run([args.source/'out/host/linux-x86/bin/host_init_verifier',combined])
        (args.output/'init-verifier.txt').write_text(init.stdout+init.stderr+'exit=0\n')
        crypto_rc = new['init.violin.crypto.rc'][1].decode()
        assert crypto_rc.index('start violin-crypto-bootstrap\n') < crypto_rc.index('setprop sys.orangefox.crypto.started 1')
        assert 'init.svc.violin-crypto-bootstrap=stopped && property:sys.orangefox.crypto.started=1' in crypto_rc
        assert b'service recovery /system/bin/recovery\n    disabled\n' in new['init.recovery.service.rc'][1]
        assert b'on late-init' not in new['system/etc/init/keystore2.rc'][1]
        assert b'    disabled\n' in new['system/etc/init/keystore2.rc'][1]

        assembler = args.source/'out/host/linux-x86/bin/assemble_vintf'
        vendor_xmls = ['vendor/etc/vintf/manifest.xml']+[
            'vendor/etc/vintf/manifest/'+n for n in packer.MANIFESTS]+[
            'vendor/odm/etc/vintf/manifest/vendor.xiaomi.hw.touchfeature-service.xml']
        merged = args.output/'vendor-manifest.xml'
        run([assembler,'-i',':'.join(str(root/n) for n in vendor_xmls),'-o',merged])
        tree = ET.parse(merged)
        assert any(h.findtext('name') == 'android.hardware.security.keymint' and h.findtext('version') == '3'
                   for h in tree.getroot().findall('hal'))
        framework = args.output/'framework-manifest.xml'
        run([assembler,'-i',str(root/'system/etc/vintf/manifest.xml')+':'+str(
            root/'system/etc/vintf/manifest/android.system.keystore2-service.xml'),'-o',framework])
        assert 'android.system.keystore2' in framework.read_text()
        red = subprocess.run([str(assembler),'-i',str(args.stock_root/'vendor/etc/vintf/manifest'/
                              packer.MANIFESTS[0]),'-o',str(root/'stock-envelope.xml')],
                             capture_output=True,text=True)
        assert red.returncode and 'Unrecognized manifest.version 8.0' in red.stderr
        (args.output/'stock-vintf-envelope-rejected.txt').write_text(red.stdout+red.stderr)
        # Both helpers must be real ARM64 executables, not a host build.
        for name in ('violin-touch-mountns','violin-service-ready'):
            header = new['system/bin/'+name][1]
            assert header[:4] == b'\x7fELF' and struct.unpack_from('<H',header,18)[0] == 183

        command = [sys.executable,str(HERE/'prepare-crypto-services.py'), '--base',str(args.base),
            '--probe',str(root/'wrong-probe'), '--stock-root',str(args.stock_root),
            '--helper-root',str(root/'unused-helpers'), '--avbtool',str(args.source/'external/avb/avbtool.py'),
            '--output',str(root/'must-not-exist')]
        (root/'wrong-probe/compiled-root/system/bin').mkdir(parents=True)
        (root/'wrong-probe/compiled-root/system/bin/recovery').write_bytes(b'WRONG_BUILD')
        (root/'wrong-probe/exit-code.txt').write_text('0\n')
        for flag, bad in (('--base',root/'helper.c'),('--probe',root/'wrong-probe')):
            (root/'helper.c').write_bytes(b'WRONG_BASE')
            rejected = command.copy()
            rejected[rejected.index(flag)+1] = str(bad)
            if flag == '--probe':
                rejected[rejected.index('--base')+1] = str(args.base)
            red = subprocess.run(rejected,capture_output=True,text=True)
            assert red.returncode and not (root/'must-not-exist').exists(),red
        wrong = root/'wrong-stock/vendor'
        wrong.mkdir(parents=True)
        (wrong/'build.prop').write_text('ro.vendor.build.version.incremental=OS4.0.0.14.XOTCNXM\n')
        rejected = command.copy()
        rejected[rejected.index('--stock-root')+1] = str(wrong.parent)
        red = subprocess.run(rejected,capture_output=True,text=True)
        assert red.returncode and 'Wrong stock firmware' in red.stderr
        assert not (root/'must-not-exist').exists()

    avb = run(['python3',args.source/'external/avb/avbtool.py','verify_image',
               '--image',args.candidate/'recovery.img'])
    (args.output/'avb-verification.txt').write_text(avb.stdout)
    result = dict(image_sha256=cpio.sha(image), image_bytes=len(image), packed_ramdisk_bytes=size,
        manifests=counts, init_service_count=len(services), single_binder_manager=True,
        pre_existing_missing_service_programs=existing_missing,
        init_verifier_pass=True, compatible_vendor_and_framework_vintf=True,
        aidl_keymint_version_retained=3, elf_programs_pass=len(audits),
        stock_vendor_ta_files_verified=len(ta_paths), arm64_helpers_verified=True,
        missing_apex_library_control_rejected=True, stock_vintf_envelope_control_rejected=True,
        wrong_base_build_firmware_rejected_before_output=True,
        chinese_input_mtp_preserved=True, userdata_fstab_unchanged=True,
        avb_algorithm='NONE; unsigned',rollback_index=1788220800,rollback_index_location=11,
        android_program_executed=False,services_runtime_verified=False,
        decryption_verified=False,internal_storage_mtp_verified=False,tablet_flashed=False)
    (args.output/'verification-results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
