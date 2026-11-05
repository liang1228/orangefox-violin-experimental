"""Offline OS3 Mitee prerequisite audit. Does not execute Android programs."""
import argparse
import importlib.util
import json
from pathlib import Path


FIRMWARE = "OS3.0.305.0.WOTCNXM"
PROGRAMS = (
    "bin/tee-supplicant",
    "bin/hw/android.hardware.security.keymint@3.0-service.mitee",
    "bin/hw/android.hardware.gatekeeper-service.mitee",
)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stock-root", type=Path, required=True)
    ap.add_argument("--system-libs", type=Path, required=True)
    ap.add_argument("--recovery-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    # Reject a different firmware before creating an output file.
    for relative, prop in (("vendor/build.prop", "ro.vendor.build.version.incremental"),
                           ("odm/etc/build.prop", "ro.odm.build.version.incremental")):
        lines = (args.stock_root / relative).read_text().splitlines()
        if f"{prop}={FIRMWARE}" not in lines:
            ap.error(f"Expected matching {FIRMWARE} in {relative}")
    if args.output.exists():
        ap.error("Use a new output file; previous evidence is preserved")
    spec = importlib.util.spec_from_file_location(
        "elf_closure", Path(__file__).with_name("check-elf-closure.py"))
    elf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(elf)
    roots = [args.stock_root / "vendor/lib64", args.stock_root / "odm/lib64",
             args.system_libs, args.recovery_root / "system/lib64"]
    baseline = [roots[0], roots[1], roots[3]]
    checks = []
    for relative in PROGRAMS:
        program = args.stock_root / "vendor" / relative
        before = elf.audit(program, baseline)
        after = elf.audit(program, roots)
        checks.append({"program": relative,
                       "without_system_support_missing": before["missing_libraries"],
                       "with_system_support": after})
    passed = all(not item["with_system_support"]["missing_libraries"] and
                 not item["with_system_support"]["unresolved_strong_symbols"]
                 for item in checks)
    result = {"firmware": FIRMWARE, "static_closures_pass": passed,
              "runtime_executed": False, "tablet_files_written": False,
              "decryption_tested": False, "checks": checks}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"static_closures_pass": passed,
                      "checks": [{"program": x["program"],
                                  "before_missing": x["without_system_support_missing"],
                                  "after_missing": x["with_system_support"]["missing_libraries"],
                                  "after_unresolved": x["with_system_support"]["unresolved_strong_symbols"]}
                                 for x in checks]}, indent=2))
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
