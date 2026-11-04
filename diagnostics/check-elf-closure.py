"""Static DT_NEEDED and strong-symbol audit; does not execute target binaries.

Library directories are searched in the supplied runtime order. This is not
proof of linker namespaces, Binder services, dlopen paths, or ABI semantics.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def inspect(path):
    dynamic = subprocess.run(["readelf", "-dW", str(path)], capture_output=True,
                             text=True, check=True).stdout
    table = subprocess.run(["readelf", "--dyn-syms", "--wide", str(path)],
                           capture_output=True, text=True, check=True).stdout
    defined, undefined = set(), set()
    for line in table.splitlines():
        row = re.match(r"\s*\d+:\s+[0-9a-fA-F]+\s+\d+\s+.+?\s+"
                       r"(LOCAL|GLOBAL|WEAK|UNIQUE)\s+(\w+)\s+(\w+)\s+(\S+)", line)
        if row is None:
            continue
        bind, visibility, ndx, name = row.groups()
        if ndx == "UND":
            if bind == "GLOBAL":
                undefined.add(name)
        elif bind in ("GLOBAL", "WEAK") and visibility in ("DEFAULT", "PROTECTED"):
            defined.add(name.replace("@@", "@"))
            if "@@" in name or "@" not in name:
                defined.add(name.split("@")[0])
    return re.findall(r"Shared library: \[(.*?)\]", dynamic), defined, undefined


def audit(program, library_dirs):
    queue, objects, missing = [program], {}, set()
    while queue:
        path = queue.pop(0)
        if path.name in objects:
            continue
        needed, exports, imports = inspect(path)
        objects[path.name] = (path, needed, exports, imports)
        for name in needed:
            found = next((root / name for root in library_dirs if (root / name).is_file()), None)
            if found is None:
                missing.add(name)
            else:
                queue.append(found)
    exports = set().union(*(item[2] for item in objects.values()))
    unresolved = {name: sorted(item[3] - exports) for name, item in objects.items()
                  if item[3] - exports}
    return {"program": str(program), "runtime_executed": False,
            "scope": "Static closure/export presence only; not Android linker or ABI acceptance",
            "missing_libraries": sorted(missing), "unresolved_strong_symbols": unresolved,
            "objects": {n: {"path": str(p), "needed": needed,
                             "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                        for n, (p, needed, _, _) in objects.items()}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--program", type=Path, required=True)
    ap.add_argument("--library-dir", type=Path, action="append", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = audit(args.program, args.library_dir)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "objects"}, indent=2))
    raise SystemExit(bool(result["missing_libraries"] or result["unresolved_strong_symbols"]))
