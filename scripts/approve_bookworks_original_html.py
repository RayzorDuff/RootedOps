#!/usr/bin/env python3
"""Prepare or verify a separately reviewed original-HTML approval receipt.

Preparation does not approve anything. The reviewer must explicitly run --approve
after comparing the source HTML to the intended public publication.
"""
import argparse
import hashlib
import json
from pathlib import Path

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--approve', action='store_true', help='Explicitly approve exact original HTML bytes for WordPress draft staging')
    args = parser.parse_args()
    root = args.release.resolve()
    html = args.html.resolve()
    receipt_file = root / 'approval.json'
    payload_file = root / 'wordpress.json'
    receipt = json.loads(receipt_file.read_text())
    payload = json.loads(payload_file.read_text())
    assert receipt['approval'] == 'approved-for-wordpress-draft'
    assert receipt['payload_sha256'] == digest(payload_file)
    assert receipt['publication_key'] == payload['publication_id'] + ':' + payload['profile']
    assert receipt['source_commit'] == payload['source_commit']
    assert html.is_file() and html.suffix.lower() == '.html'
    approval = {
        'schema_version': 1,
        'approval': 'approved-original-html-for-wordpress-draft' if args.approve else 'pending-review',
        'publication_key': receipt['publication_key'],
        'source_commit': receipt['source_commit'],
        'approval_receipt_sha256': digest(receipt_file),
        'original_html_sha256': digest(html),
        'original_html_filename': html.name,
    }
    dest = root / 'original-html-approval.json'
    if dest.exists():
        raise SystemExit(f'Refusing to overwrite existing approval: {dest}')
    dest.write_text(json.dumps(approval, indent=2) + '\n')
    print(f'Wrote {dest} ({approval["approval"]})')

if __name__ == '__main__':
    main()
