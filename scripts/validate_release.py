#!/usr/bin/env python3
"""Verify RootedOps release metadata is internally consistent."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
failures = []
if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?", version):
    failures.append("VERSION is not semantic versioning")
if f"Current version: **{version}**." not in (ROOT / "README.md").read_text(encoding="utf-8"):
    failures.append("README.md version does not match VERSION")
if not re.search(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", (ROOT / "doc/CHANGELOG.md").read_text(encoding="utf-8"), re.M):
    failures.append("doc/CHANGELOG.md has no dated heading for VERSION")
if not (ROOT / f"releases/v{version}/RELEASE_NOTES.md").exists():
    failures.append("versioned release notes are missing")
if failures:
    raise SystemExit("Release check failed:\n- " + "\n- ".join(failures))
