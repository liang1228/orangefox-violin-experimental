"""Host-only overmount regression. All mounts stay in a disposable namespace."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def child(root):
    root = Path(root)
    before = (root / "data/sentinel").read_text()
    (root / "ready").touch()
    deadline = time.monotonic() + 10
    while not (root / "mounted").exists():
        if time.monotonic() > deadline:
            raise TimeoutError("Parent did not finish the test mount")
        time.sleep(0.02)
    after = (root / "data/sentinel").read_text()
    print(json.dumps({"before": before, "after": after,
                      "child_mount_namespace": os.readlink("/proc/self/ns/mnt")}))


def isolated(wrapper):
    with tempfile.TemporaryDirectory(prefix="violin-mountns-") as temp:
        root = Path(temp)
        for name, value in (("data", "RAM"), ("userdata", "USERDATA_TEST")):
            (root / name).mkdir()
            (root / name / "sentinel").write_text(value)
        # Model Android init's shared mounts. With a private parent, even the
        # unsafe MS_SLAVE variant would appear to work in this regression.
        subprocess.run(["mount", "--bind", str(root), str(root)], check=True)
        subprocess.run(["mount", "--make-shared", str(root)], check=True)
        process = subprocess.Popen([str(wrapper), sys.executable, __file__,
                                    "--child", str(root)], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        mounted = False
        try:
            deadline = time.monotonic() + 10
            while not (root / "ready").exists():
                if process.poll() is not None:
                    raise RuntimeError("Child did not become ready: " + process.communicate()[1])
                if time.monotonic() > deadline:
                    raise TimeoutError("Child did not become ready")
                time.sleep(0.02)
            # This is a synthetic directory on the host, never a device partition.
            subprocess.run(["mount", "--bind", str(root / "userdata"),
                            str(root / "data")], check=True)
            mounted = True
            parent_sees = (root / "data/sentinel").read_text()
            (root / "mounted").touch()
            stdout, stderr = process.communicate(timeout=10)
            if process.returncode:
                raise RuntimeError(stderr)
            result = json.loads(stdout)
            result.update({"parent_sees": parent_sees,
                           "parent_mount_namespace": os.readlink("/proc/self/ns/mnt"),
                           "android_runtime_tested": False})
            passed = (result["before"] == result["after"] == "RAM" and
                      parent_sees == "USERDATA_TEST" and
                      result["child_mount_namespace"] != result["parent_mount_namespace"])
            result["passed"] = passed
            print(json.dumps(result, indent=2))
            return int(not passed)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if mounted:
                subprocess.run(["umount", str(root / "data")], check=True)
            subprocess.run(["umount", str(root)], check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wrapper", type=Path)
    ap.add_argument("--isolated", action="store_true")
    ap.add_argument("--child")
    args = ap.parse_args()
    if args.child:
        child(args.child)
    elif args.isolated:
        raise SystemExit(isolated(args.wrapper.resolve()))
    else:
        if args.wrapper is None:
            ap.error("--wrapper is required")
        raise SystemExit(subprocess.call([
            "unshare", "--mount", "--propagation", "private", sys.executable,
            __file__, "--isolated", "--wrapper", str(args.wrapper.resolve())]))
