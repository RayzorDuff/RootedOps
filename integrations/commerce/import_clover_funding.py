"""Prepare a reviewed settlement payload from private normalized funding CSV."""
import argparse
import csv
import json
from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[2] / 'erpnext/apps/rootedops_commerce'
sys.path.insert(0, str(APP))
from rootedops_commerce.settlement_contract import settlement_plan


def prepare(manifest, detail, policy):
    batch = json.loads(manifest.read_text())
    with detail.open(newline='') as stream:
        reader = csv.DictReader(stream)
        keys = ('kind', 'reference', 'channel', 'amount', 'erp_reference')
        if tuple(reader.fieldnames or ()) != keys:
            raise ValueError('Reviewed funding CSV header required')
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('Incomplete funding row')
    batch['records'] = [{key: value for key, value in row.items() if value} for row in rows]
    settlement_plan(batch, policy)
    return batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'detail', 'policy', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    batch = prepare(args.manifest, args.detail, json.loads(args.policy.read_text()))
    import os
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'payload': json.dumps(batch)}, stream)


if __name__ == '__main__':
    main()
