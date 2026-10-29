#!/usr/bin/env python3
"""Prepare RootedOps version files without committing or tagging."""
import argparse
import datetime as dt
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
parser.add_argument("--release-date", default=dt.date.today().isoformat())
args = parser.parse_args()
if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?", args.version):
    raise SystemExit(f"Invalid semantic version: {args.version}")
dt.date.fromisoformat(args.release_date)
if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True).stdout.strip():
    raise SystemExit("Working tree must be clean before preparing a release.")
old = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
(ROOT / "VERSION").write_text(args.version + "\n", encoding="utf-8")
readme_path = ROOT / "README.md"
readme = readme_path.read_text(encoding="utf-8")
readme = re.sub(r"^Current version: \*\*[^*]+\*\*\.$", f"Current version: **{args.version}**.", readme, count=1, flags=re.M)
readme_path.write_text(readme, encoding="utf-8")
notes = ROOT / f"releases/v{args.version}/RELEASE_NOTES.md"
notes.parent.mkdir(parents=True, exist_ok=True)
if not notes.exists():
    notes.write_text(f"# RootedOps v{args.version}\n\nRelease date: {args.release_date}\n\n## Summary\n\nTODO\n", encoding="utf-8")
print(f"Prepared RootedOps {old} -> {args.version}. Complete the changelog and notes, then run make release-check.")
