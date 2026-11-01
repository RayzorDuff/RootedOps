#!/usr/bin/env python3
"""Offline-only reviewed migration compiler. Output contains private source data."""
import argparse
import json
from pathlib import Path
from ecwid_migrate import private_write
from reviewed_catalog import compile_catalog
from history import convert_history
from copy import deepcopy


def select_catalog(source, source_keys):
    """Select complete product families without changing the full export digest.

    Reviewing one variant in isolation can silently omit its template or siblings.
    Expand that selection to the whole family; never invent absent combinations.
    The review still binds to the original complete source, not a rewritten export.
    """
    if not source_keys:
        return source
    keys=set(source_keys)
    indexed={p['source_key']:p for p in source['products']}
    if len(indexed)!=len(source['products']):
        raise ValueError('Duplicate source identities in catalog plan')
    if keys-set(indexed):
        raise ValueError('Unknown pilot source identity')
    families={indexed[k]['item'].get('parent_sku') or indexed[k]['content']['item'] for k in keys}
    selected=[p for p in source['products'] if (p['item'].get('parent_sku') or p['content']['item']) in families]
    for family in families:
        if not any(p['content']['item']==family and not p['item'].get('parent_sku') for p in selected):
            raise ValueError('Selected variation has no source template')
    result=deepcopy(source)
    result['products']=deepcopy(selected)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=['catalog','history'])
    parser.add_argument('source',type=Path)
    parser.add_argument('review',type=Path)
    parser.add_argument('--media-manifest',type=Path)
    parser.add_argument('--source-key',action='append',help='Catalog pilot source identity; includes its full exported variation family')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    source=json.loads(args.source.read_text());review=json.loads(args.review.read_text())
    if args.kind=='catalog':
        media=json.loads(args.media_manifest.read_text()) if args.media_manifest else []
        selected=select_catalog(source,args.source_key)
        result=compile_catalog(selected,review,media)
        result['coverage']={'full_source_product_records':len(source['products']),
                            'selected_source_keys':[p['source_key'] for p in selected['products']],
                            'destination_verified':False}
    else:
        if args.source_key:parser.error('--source-key applies only to catalog')
        result=convert_history(source,review)
    private_write(args.output,result)
    print('Private reviewed migration plan written; no external writes performed.')

if __name__=='__main__':main()
