#!/usr/bin/env python3
"""Record actual OrangeFox checkouts in a repo-generated source inventory."""
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

source, original, output = map(pathlib.Path, sys.argv[1:])


def git(path, *args):
    return subprocess.check_output(
        ["git", "-C", str(source / path), *args], text=True
    ).strip()


tree = ET.parse(original)
root = tree.getroot()
assert not any(r.get("name") == "OrangeFox" for r in root.findall("remote"))
root.insert(0, ET.Element("remote", name="OrangeFox", fetch="https://gitlab.com/OrangeFox"))
projects = [p for p in root.findall("project") if p.get("path") == "bootable/recovery"]
assert len(projects) == 1
recovery = projects[0]
assert git("bootable/recovery", "remote", "get-url", "origin") == (
    "https://gitlab.com/OrangeFox/bootable/Recovery.git"
)
assert recovery.get("revision") == git("bootable/recovery", "rev-parse", "HEAD")
recovery.attrib.update(name="bootable/Recovery", remote="OrangeFox", upstream="fox_12.1")
recovery.attrib.pop("dest-branch", None)
assert not any(p.get("path") == "vendor/recovery" for p in root.findall("project"))
assert git("vendor/recovery", "remote", "get-url", "origin") == (
    "https://gitlab.com/OrangeFox/vendor/recovery.git"
)
root.append(ET.Element("project", name="vendor/recovery", path="vendor/recovery",
                       remote="OrangeFox", revision=git("vendor/recovery", "rev-parse", "HEAD")))
ET.indent(tree, space="  ")
output.parent.mkdir(parents=True, exist_ok=True)
tree.write(output, encoding="utf-8", xml_declaration=True)
