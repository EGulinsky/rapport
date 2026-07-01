#!/usr/bin/env python3
"""Rendert eine JUnit-XML-Testreport-Datei als Markdown für GITHUB_STEP_SUMMARY.
Funktioniert sowohl für pytest- als auch für vitest-JUnit-Ausgaben (beide
folgen dem gleichen <testsuite tests= failures= errors= skipped=>-Schema).

Usage: junit_summary.py <report.xml> <Titel>
"""
import sys
import xml.etree.ElementTree as ET

path, title = sys.argv[1], sys.argv[2]

try:
    root = ET.parse(path).getroot()
except FileNotFoundError:
    print(f"### ⚠️ {title}: kein Testreport gefunden ({path})")
    sys.exit(0)

suites = root.findall(".//testsuite") if root.tag != "testsuite" else [root]

total = failures = errors = skipped = 0
failed_names: list[str] = []

for suite in suites:
    total += int(suite.get("tests", 0))
    failures += int(suite.get("failures", 0))
    errors += int(suite.get("errors", 0))
    skipped += int(suite.get("skipped", 0))
    for tc in suite.findall("testcase"):
        if tc.find("failure") is not None or tc.find("error") is not None:
            cls = tc.get("classname", "")
            name = tc.get("name", "")
            failed_names.append(f"{cls}::{name}" if cls else name)

passed = total - failures - errors - skipped
ok = failures == 0 and errors == 0
status = "✅" if ok else "❌"

lines = [
    f"### {status} {title}: {passed}/{total} bestanden",
    "",
    "| Bestanden | Fehlgeschlagen | Fehler | Übersprungen |",
    "|---|---|---|---|",
    f"| {passed} | {failures} | {errors} | {skipped} |",
]
if failed_names:
    lines.append("")
    lines.append("**Fehlgeschlagen:**")
    lines.extend(f"- `{n}`" for n in failed_names)

print("\n".join(lines))
