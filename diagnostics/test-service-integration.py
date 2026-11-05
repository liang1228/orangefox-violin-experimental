"""Host-only startup, Binder-checker and actual RAM-view restart regressions."""
import argparse
import json
import os
import re
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def run(command, expected=0, **kwargs):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, **kwargs)
    assert result.returncode == expected, (command, result.returncode, result.stdout, result.stderr)
    return result


MOCK = r'''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
root = Path(os.environ['VIOLIN_FIXTURE'])
state = json.loads((root/'state.json').read_text())
command = Path(sys.argv[0]).name
args = sys.argv[1:]
with (root/'commands.jsonl').open('a') as log:
    log.write(json.dumps([command]+args)+'\n')
scenario = state['scenario']
if command == 'getprop':
    print(state['properties'].get(args[0], ''))
elif command == 'setprop':
    state['properties'][args[0]] = args[1]
elif command == 'sha256sum':
    if scenario == 'integrity-fail': sys.exit(1)
elif command == 'violin-touch-mountns':
    if scenario == 'view-fail': sys.exit(1)
elif command == 'violin-service-ready':
    stage = state['properties'].get('sys.orangefox.crypto.stage')
    if scenario == stage+'-fail': sys.exit(1)
elif command == 'mount':
    if scenario == 'mount-fail': sys.exit(1)
    persist = Path(args[-1])
    for name in ('data', 'fdsd'): (persist/name).mkdir(exist_ok=True)
(root/'state.json').write_text(json.dumps(state))
'''


def startup_tests(root):
    results = []
    for scenario in ('ok', 'integrity-fail', 'view-fail', 'wrong-patch', 'mitee-disabled',
                     'touch-ram-view-fail', 'mount-fail', 'security-registration-fail',
                     'keystore-registration-fail'):
        case = root / scenario
        case.mkdir()
        for name in ('system/bin', 'tmp', 'mnt/vendor/persist', 'dev/block/by-name'):
            (case / name).mkdir(parents=True, exist_ok=True)
        tool = case / 'system/bin/mock'
        tool.write_text(MOCK)
        tool.chmod(0o755)
        for name in ('getprop', 'setprop', 'sha256sum', 'violin-touch-mountns',
                     'violin-service-ready', 'mount', 'chown', 'chmod'):
            (tool.parent / name).symlink_to('mock')
        os.mknod(case/'dev/block/by-name/persist', stat.S_IFBLK | 0o600, os.makedev(7, 255))
        for name in ('tee0', 'teepriv0', 'rpmb0'):
            os.mknod(case/'dev'/name, stat.S_IFCHR | 0o600, os.makedev(1, 3))
        properties = {'ro.product.device': 'violin', 'init.svc.violin-crypto-bootstrap': 'running',
            'ro.build.version.release': '16', 'ro.build.version.security_patch': '2026-09-01',
            'ro.vendor.build.security_patch': '2026-09-01', 'ro.hardware.gatekeeper': 'mitee'}
        if scenario == 'wrong-patch': properties['ro.build.version.security_patch'] = '2022-04-05'
        if scenario == 'mitee-disabled': properties['ro.boot.mitee_disable'] = 'true'
        (case/'state.json').write_text(json.dumps(dict(properties=properties, scenario=scenario)))
        script = (HERE/'start-violin-crypto.sh').read_text()
        script = re.sub(r'/(system|sbin|tmp|mnt|dev)(?=/|\b)',
                        lambda match: str(case) + match[0], script)
        # Keep native host tools available after the mocked Android commands.
        script = re.sub(r'^(export PATH=.*)$', r'\1:/usr/bin:/bin', script, flags=re.M)
        path = case/'startup.sh'
        path.write_text(script)
        result = subprocess.run(['/bin/sh', str(path)], env={**os.environ, 'VIOLIN_FIXTURE': str(case)},
                                capture_output=True, text=True, timeout=10)
        state = json.loads((case/'state.json').read_text())
        commands = [json.loads(s) for s in (case/'commands.jsonl').read_text().splitlines()]
        assert ['setprop', 'ctl.start', 'recovery'] in commands, (scenario, result)
        starts = [c[2] for c in commands if c[:2] == ['setprop', 'ctl.start']]
        assert starts[-1] == 'recovery', (scenario, starts)
        assert (result.returncode == 0) == (scenario == 'ok'), (scenario, result)
        assert state['properties'].get('sys.orangefox.crypto.services_ready') == ('1' if scenario == 'ok' else '0')
        mounts = [c for c in commands if c[0] == 'mount']
        assert all(c[-1] == str(case/'mnt/vendor/persist') for c in mounts), mounts
        if scenario == 'ok':
            assert starts == ['violin-servicemanager', 'violin-touchfeature', 'violin-tee',
                              'violin-keymint', 'violin-gatekeeper', 'keystore2', 'recovery'], starts
            assert state['properties']['sys.orangefox.crypto.stage'] == 'services-registered'
        if scenario in ('integrity-fail', 'view-fail', 'wrong-patch', 'mitee-disabled', 'touch-ram-view-fail'):
            assert not mounts and 'violin-tee' not in starts
        if scenario == 'security-registration-fail': assert 'keystore2' not in starts
        results.append(dict(scenario=scenario, passed=True, exit=result.returncode))
    return results


def binder_checker_tests(root):
    source = (HERE/'violin-service-ready.c').read_text()
    source = source.replace('#include <android/binder_ibinder.h>','').replace(
        '#include <android/binder_manager.h>','')
    source = source.replace('clock_gettime(', 'fake_clock(').replace('usleep(', 'fake_sleep(')
    prelude = r'''
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
typedef struct { int unused; } AIBinder;
static AIBinder handle;
static int granted, released, calls, ticks;
static const char *mode;
static void check_refs(void) {
    if (granted != released) _Exit(88);
    printf("%d %d %d\n", granted, released, calls);
}
__attribute__((constructor)) static void setup(void) {
    mode = getenv("BINDER_FIXTURE_MODE");
    atexit(check_refs);
}
static AIBinder *AServiceManager_checkService(const char *name) {
    (void)name;
    ++calls;
    if (!strcmp(mode,"missing") || (!strcmp(mode,"late") && calls <= 2)) return NULL;
    ++granted;
    return &handle;
}
static int AIBinder_isAlive(AIBinder *b) { (void)b; return strcmp(mode,"dead") != 0; }
static void AIBinder_decStrong(AIBinder *b) { (void)b; ++released; }
static int fake_clock(int id, struct timespec *now) {
    (void)id;
    now->tv_sec = ticks++ / 3;
    now->tv_nsec = 0;
    return 0;
}
static int fake_sleep(unsigned int us) { (void)us; return 0; }
'''
    path, binary = root/'checker.c', root/'checker'
    path.write_text(prelude+source)
    run(['cc','-O2','-Wall','-Wextra','-Werror',path,'-o',binary])
    cases = [('all',['1','first','second'],0), ('late',['1','first','second'],0),
             ('missing',['1','first','second'],1), ('dead',['1','first','second'],1),
             ('all',['0','first'],64), ('all',['61','first'],64), ('all',['bad','first'],64)]
    for mode,args,expected in cases:
        result = run([binary]+args, expected=expected,
                     env={**os.environ,'BINDER_FIXTURE_MODE':mode})
        granted,released,calls = map(int,result.stdout.split())
        assert granted == released
        if args[0] == '1': assert calls >= 2
    return dict(cases=len(cases), reference_counts_balanced=True,
                missing_and_dead_services_rejected=True, late_registration_accepted=True,
                binder_host_stubs=True)


def mount_tests():
    with tempfile.TemporaryDirectory(prefix='violin-service-view-') as temp:
        root = Path(temp)
        run(['mount', '-t', 'tmpfs', '-o', 'size=4m', 'tmpfs', root])
        # A shared parent is necessary to expose propagation regressions.
        run(['mount', '--make-shared', root])
        try:
            for name in ('data', 'vendor', 'odm', 'persist', 'userdata', 'realvendor', 'realodm', 'realpersist'):
                (root/name).mkdir()
                (root/name/'sentinel').write_text('RAM' if name in ('data','vendor','odm','persist') else 'DISK_TEST')
            source = (HERE/'violin-touch-mountns.c').read_text()
            for original, replacement in (('/data', 'data'), ('/vendor', 'vendor'), ('/odm','odm'),
                                           ('/mnt/vendor/persist', 'persist'), ('/tmp', '')):
                source = source.replace('"'+original+'"', '"'+str(root/replacement)+'"')
            (root/'helper.c').write_text(source)
            helper = root/'helper'
            run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', root/'helper.c', '-o', helper])
            view = root/'view'
            run([helper, '--capture', view])
            script = 'import json; from pathlib import Path; print(json.dumps([Path(p).read_text() for p in __import__("sys").argv[1:]]))'
            reader = [sys.executable, '-c', script] + [root/name/'sentinel' for name in ('data','vendor','odm','persist')]
            before = json.loads(run([helper, '--ram-view', view]+reader).stdout)
            for src, target in (('userdata', 'data'), ('realvendor','vendor'), ('realodm','odm'), ('realpersist','persist')):
                run(['mount', '--bind', root/src, root/target])
            parent = [(root/name/'sentinel').read_text() for name in ('data','vendor','odm','persist')]
            restarted = json.loads(run([helper, '--ram-view', view]+reader).stdout)
            unsafe = json.loads(run([helper]+reader).stdout)
            assert before == restarted == ['RAM']*4 and parent == unsafe == ['DISK_TEST']*4
            run([helper, '--capture', root/'late-view'], expected=1)
            assert not (root/'late-view').exists()
            fake = root/'fake'
            fake.mkdir()
            for name in ('data','vendor','odm','persist'): (fake/name).mkdir()
            run([helper, '--ram-view', fake]+reader, expected=1)
            return dict(before=before, parent=parent, restarted=restarted, unsafe_control=unsafe,
                        mounted_parent_capture_refused=True, unmounted_fake_view_refused=True,
                        android_executed=False, passed=True)
        finally:
            # A single temporary tmpfs tree, all inside this disposable namespace.
            run(['umount', '-l', root])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--mount-isolated', action='store_true')
    args = ap.parse_args()
    if args.mount_isolated:
        print(json.dumps(mount_tests(), indent=2))
        return
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='violin-startup-stubs-') as temp:
        startup = startup_tests(Path(temp))
        binder = binder_checker_tests(Path(temp))
    mounts = json.loads(run(['unshare', '--mount', '--propagation', 'private', sys.executable,
                             __file__, '--mount-isolated']).stdout)
    result = dict(startup_cases=startup, binder_checker=binder, ram_view_restart=mounts, startup_host_stubs=True,
                  tablet_program_executed=False, decryption_verified=False)
    (args.output/'host-tests.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
