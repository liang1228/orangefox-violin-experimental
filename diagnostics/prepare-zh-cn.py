"""Use the pinned OrangeFox Chinese translation; audit keys and placeholders.

Only the verified upstream MD5 checkbox typo and two missing entries are fixed.
The font and bulk translation stay upstream originals. No device commands.
"""
import argparse
import collections
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

LANG_SHA = "9368a61bf395ac8c686c4a1933f786df963590249b082a7437c47ca1b7c96ed9"
FONT_SHA = "e4bca8df123ce01b104780f576ea1a58b9a5ff1662a91124b6d3180cb6c88212"
UPSTREAM = "https://gitlab.com/OrangeFox/bootable/Recovery/-/blob/6bd902d14f754ab98a7cccc5598f7b9d135cfc38/gui/theme/extra-languages/languages/zh_CN.xml"


def strings(data):
    root = ET.fromstring(data)
    result = {}
    for node in root.findall(".//string"):
        name, value = node.attrib["name"], node.text or ""
        if name in result and result[name] != value:
            raise ValueError("Conflicting duplicate translation: " + name)
        result[name] = value
    return root, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    theme = args.source / "gui/theme"
    original = (theme / "extra-languages/languages/zh_CN.xml").read_bytes()
    font = theme / "extra-languages/fonts/wqy-microhei.ttf"
    assert hashlib.sha256(original).hexdigest() == LANG_SHA
    assert hashlib.sha256(font.read_bytes()).hexdigest() == FONT_SHA
    text = original.decode("utf-8")
    # The upstream string mistakenly contains the unrelated 'MD5 not found' error.
    wrong = '<string name="restore_md5_chk">找不到 \'{1}\' 的 MD5 文件。</string>'
    assert text.count(wrong) == 1
    text = text.replace(wrong, '<string name="restore_md5_chk">校验备份文件的 MD5</string>')
    text = text.replace("<display>Chinese Simplified</display>", "<display>简体中文</display>")
    assert text.count("</resources>") == 1
    text = text.replace("</resources>",
                        '    <string name="kbyte"> KB</string>\n'
                        '    <string name="remove_factory_reset_protection">移除恢复出厂设置保护（FRP）</string>\n'
                        '    </resources>')
    root, chinese = strings(text)
    _, english = strings((theme / "common/languages/en.xml").read_bytes())
    assert not english.keys() - chinese.keys(), sorted(english.keys() - chinese.keys())
    tokens = lambda value: collections.Counter(re.findall(r"%[A-Za-z_][A-Za-z0-9_]*%|\{[0-9]+\}", value))
    assert not [key for key in english if tokens(english[key]) != tokens(chinese[key])]
    fonts = {node.attrib["filename"] for node in root.findall(".//resource")
             if node.get("type") == "fontoverride"}
    assert fonts == {font.name}
    args.output.mkdir(parents=True, exist_ok=False)
    language = args.output / "twres/languages/zh_CN.xml"
    language.parent.mkdir(parents=True)
    language.write_text(text, encoding="utf-8")
    destination = args.output / "twres/fonts"
    destination.mkdir(parents=True)
    shutil.copyfile(font, destination / font.name)
    notice = theme / "extra-languages/fonts/wqy-microhei_README.txt"
    shutil.copyfile(notice, destination / notice.name)
    report = {"upstream": UPSTREAM, "upstream_language_sha256": LANG_SHA,
              "language_sha256": hashlib.sha256(language.read_bytes()).hexdigest(),
              "font_sha256": FONT_SHA, "english_keys_covered": len(english),
              "missing_english_keys": [], "placeholder_mismatches": [],
              "changed_text_keys": ["restore_md5_chk", "kbyte", "remove_factory_reset_protection"],
              "language_display": "简体中文", "device_display_verified": False}
    (args.output / "language-audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
