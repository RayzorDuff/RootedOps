#!/usr/bin/env python3
"""Validate and install the Board Working Documents manifest from an approved release.

The Board Portal shortcode reads working-documents.json from a read-only Docker
bind. This operator-side helper updates that file on the host rclone mount.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

SOURCE = "rooted-psyche-corporate-record-book/chapters/11-board-editable-document-register.md"
URL = re.compile(r"https://docs\.google\.com/(?:document|spreadsheets)/d/[A-Za-z0-9_-]+(?:/edit)?(?:\?[^#]*)?\Z")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(release: Path) -> tuple[Path | None, dict]:
    receipt = json.loads((release / "approval.json").read_text(encoding="utf-8"))
    expected = receipt.get("working_documents_sha256")
    if expected is None:
        # Older approved releases have no manifest. Preserve their behavior.
        print("Legacy Board release: no bundled Working Documents manifest.")
        return None, receipt
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("Invalid approved Working Documents digest")
    source = release / "working-documents.json"
    if source.is_symlink() or not source.is_file() or sha(source) != expected:
        raise ValueError("Approved Working Documents file missing or checksum mismatch")
    data = json.loads(source.read_text(encoding="utf-8"))
    docs = data.get("documents")
    if data.get("schema_version") != 1 or data.get("source") != SOURCE:
        raise ValueError("Unsupported Working Documents manifest schema/source")
    if data.get("source_commit") != receipt.get("source_commit"):
        raise ValueError("Manifest and approved WordPress release revisions differ")
    if not isinstance(docs, list) or not 1 <= len(docs) <= 100:
        raise ValueError("Invalid Working Documents count")
    if receipt.get("working_documents_count") != len(docs):
        raise ValueError("Manifest document count differs from approval")
    seen = set()
    for item in docs:
        if not isinstance(item, dict):
            raise ValueError("Invalid document entry")
        title, url, status = (item.get(k) for k in ("title", "url", "status"))
        if not all(isinstance(v, str) for v in (title, url, status)):
            raise ValueError("Missing document title, URL or status")
        if not title or len(title) > 256 or not status or len(status) > 700:
            raise ValueError("Document title/status out of bounds")
        if not URL.fullmatch(url) or url in seen:
            raise ValueError("Invalid or duplicate Google Docs URL")
        seen.add(url)
    return source, receipt


def run(release: Path, supplements: Path, mode: str) -> None:
    source, receipt = validate(release)
    if source is None:
        return
    if supplements.is_symlink() or not supplements.is_dir():
        raise ValueError("Board supplements directory unavailable")
    target = supplements / "working-documents.json"
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError("Refusing non-regular manifest target")
    expected = receipt["working_documents_sha256"]
    current = sha(target) if target.is_file() else None
    print(f"Board Working Documents: {receipt['working_documents_count']} links")
    print(f"Current checksum: {current or '(missing)'}")
    print(f"Approved checksum: {expected}")
    if mode != "promote":
        print("Manifest preflight only; no files modified.")
        return
    if current == expected:
        print("Working Documents manifest already current.")
        return
    # A recoverable snapshot is retained before modifying a prior manifest.
    if current is not None:
        backup = supplements / f"working-documents.before-{current[:16]}.json"
        if backup.exists():
            if backup.is_symlink() or sha(backup) != current:
                raise ValueError("Existing manifest backup differs; refusing overwrite")
        else:
            shutil.copyfile(target, backup)
            if sha(backup) != current:
                raise ValueError("Manifest backup verification failed")
        print(f"Previous manifest retained: {backup.name}")
    # Same-directory staging is required for atomic rename on the mounted FS.
    fd, tmp = tempfile.mkstemp(prefix=".working-documents-", suffix=".json", dir=supplements)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(source.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        if sha(Path(tmp)) != expected:
            raise ValueError("Staged manifest checksum mismatch")
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if sha(target) != expected:
        raise ValueError("Promoted manifest failed checksum verification")
    print("Working Documents manifest promoted and verified.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--supplements", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=["check", "stage", "promote"])
    args = parser.parse_args()
    try:
        run(args.release.resolve(), args.supplements, args.mode)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.exit(f"Board manifest deployment stopped: {exc}")


if __name__ == "__main__":
    main()
