#!/usr/bin/env python3
"""Offline-only reviewed migration compiler. Output contains private source data."""
import argparse
import json
from pathlib import Path
from ecwid_migrate import private_write
from reviewed_catalog import compile_catalog
from history import convert_history


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=['catalog','history'])
    parser.add_argument('source',type=Path)
    parser.add_argument('review',type=Path)
    parser.add_argument('--media-manifest',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    source=json.loads(args.source.read_text());review=json.loads(args.review.read_text())
    if args.kind=='catalog':
        media=json.loads(args.media_manifest.read_text()) if args.media_manifest else []
        result=compile_catalog(source,review,media)
    else:result=convert_history(source,review)
    private_write(args.output,result)
    print('Private reviewed migration plan written; no external writes performed.')

if __name__=='__main__':main()
