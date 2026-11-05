"""Verify the local compile probe and synthetic host mount regression only."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent


def run(args, expected=0):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True)
    if result.returncode != expected:
        raise RuntimeError(f"Unexpected exit {result.returncode}: {args}\n"
                           f"{result.stdout}\n{result.stderr}")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", type=Path, required=True)
    ap.add_argument("--stock-root", type=Path, required=True)
    ap.add_argument("--ndk", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    assert (args.probe / "exit-code.txt").read_text().strip() == "0"
    root = args.probe / "compiled-root"
    spec = importlib.util.spec_from_file_location("elf", HERE / "check-elf-closure.py")
    elf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(elf)
    audits = []
    for name in ("recovery", "keystore2"):
        audit = elf.audit(root / "system/bin" / name, [root / "system/lib64"])
        assert not audit["missing_libraries"] and not audit["unresolved_strong_symbols"], audit
        audits.append(audit)
    # Capture the build flags as well as the successful compiler exit.
    assert "TW_INCLUDE_CRYPTO := true" in (args.probe / "BoardConfig.crypto.mk").read_text()
    assert "TW_INCLUDE_CRYPTO" not in (args.probe / "BoardConfig.original.mk").read_text()

    source = HERE / "violin-touch-mountns.c"
    host = args.output / "touch-mountns-host"
    slave_source = args.output / "touch-mountns-slave-control.c"
    slave = args.output / "touch-mountns-slave-control"
    slave_source.write_text(source.read_text().replace("MS_REC | MS_PRIVATE", "MS_REC | MS_SLAVE"))
    for src, dest in ((source, host), (slave_source, slave)):
        run(["cc", "-O2", "-Wall", "-Wextra", "-Werror", src, "-o", dest])
    test = HERE / "test-touch-mountns.py"
    positive = json.loads(run([sys.executable, test, "--wrapper", host]).stdout)
    negative = json.loads(run([sys.executable, test, "--wrapper", slave], expected=1).stdout)
    assert positive["passed"] and not negative["passed"]
    assert negative["after"] == "USERDATA_TEST", negative
    (args.output / "mount-private-pass.json").write_text(json.dumps(positive, indent=2) + "\n")
    (args.output / "mount-slave-fail-control.json").write_text(json.dumps(negative, indent=2) + "\n")

    # This NDK was unpacked on Windows: clang/ld.lld aliases are plain text.
    # Use the real executables and a local symlink, leaving the NDK untouched.
    llvm = args.ndk / "toolchains/llvm/prebuilt/linux-x86_64"
    linker = args.output / "ld.lld"
    linker.symlink_to(llvm / "bin/lld")
    arm64 = args.output / "violin-touch-mountns-arm64"
    run([llvm / "bin/clang-21", "--target=aarch64-linux-android31",
         f"--sysroot={llvm / 'sysroot'}", f"--ld-path={linker}", "-O2",
         "-Wall", "-Wextra", "-Werror", source, "-o", arm64])
    audit = elf.audit(arm64, [root / "system/lib64"])
    assert not audit["missing_libraries"] and not audit["unresolved_strong_symbols"], audit
    audits.append(audit)
    audit_output = args.output / "mitee-with-system-support.json"
    audit_command = [sys.executable, HERE / "audit-violin-crypto.py",
                     "--stock-root", args.stock_root,
                     "--system-libs", args.stock_root / "system-support-libs",
                     "--recovery-root", root, "--output", audit_output]
    run(audit_command)
    original_result = audit_output.read_bytes()
    run(audit_command, expected=2)
    assert audit_output.read_bytes() == original_result
    with tempfile.TemporaryDirectory(prefix="violin-wrong-firmware-") as temp:
        bad = Path(temp)
        (bad / "vendor").mkdir()
        (bad / "vendor/build.prop").write_text("ro.vendor.build.version.incremental=OS4.0.0.14.XOTCNXM\n")
        wrong_command = audit_command.copy()
        wrong_command[wrong_command.index("--stock-root") + 1] = bad
        wrong_output = bad / "rejected.json"
        wrong_command[-1] = wrong_output
        run(wrong_command, expected=2)
        assert not wrong_output.exists()
    (args.output / "elf-audits.json").write_text(json.dumps(audits, indent=2) + "\n")
    result = {
        "build_exit": 0,
        "recovery_sha256": hashlib.sha256((root / "system/bin/recovery").read_bytes()).hexdigest(),
        "arm64_wrapper_sha256": hashlib.sha256(arm64.read_bytes()).hexdigest(),
        "elf_programs_pass": len(audits), "mitee_closures_pass": 3,
        "host_private_mount_pass": True, "host_slave_control_fails": True,
        "wrong_firmware_rejected_before_output": True,
        "existing_evidence_preserved": True,
        "tablet_program_executed": False, "decryption_verified": False,
        "touch_namespace_device_verified": False,
        "device_ready_image_produced": False,
    }
    (args.output / "verification-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
