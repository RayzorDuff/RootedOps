#!/usr/bin/env python3
"""Prepare immutable media and taxonomy inventory from a private Ecwid API snapshot.

No network calls. No ERP, WooCommerce or Ecwid writes. Source IDs and image
origins are summarized; original source payloads stay in operator-owned files.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from commerce_full_catalog_preflight import APPROVED_PILOT_IDS, assess

def prepare(source):
    overview=assess(source)
    products=source["products"]
    chosen=[p for p in products if int(p["id"]) in APPROVED_PILOT_IDS]
    # This exact selected-products source can be consumed by integrations/commerce/media.py.
    selected={"schema_version":source.get("schema_version",1),
              "store_id":source["store_id"],
              "categories":source["categories"],"products":chosen}
    refs={}
    for p in chosen:
        primary=p.get("originalImageUrl") or p.get("imageUrl")
        urls=[]
        if primary:urls.append(primary)
        for item in p.get("galleryImages",[]):
            uri=item.get("originalImageUrl") or item.get("url") or item.get("imageUrl")
            if uri and uri not in urls:urls.append(uri)
        refs[str(p["id"])]=urls
    all_urls=sorted({url for group in refs.values() for url in group})
    categories={str(c["id"]):c["name"] for c in source["categories"]}
    needed=sorted({str(cid) for p in products for cid in (p.get("categoryIds") or [])})
    unresolved=[cid for cid in needed if cid not in categories]
    hosts=sorted({urlsplit(url).hostname or "" for url in all_urls})
    if any(urlsplit(url).scheme!="https" for url in all_urls):
        raise ValueError("Non-HTTPS source image URL encountered")
    return selected,{"catalog_totals":{k:len(v) for k,v in overview["cohorts"].items()},
                     "source_categories":categories,
                     "required_categories":needed,
                     "unresolved_categories":unresolved,
                     "approved_pilot_products":len(chosen),
                     "pilot_products_missing_images":sum(not refs[str(p["id"])] for p in chosen),
                     "unique_selected_media_urls":len(all_urls),
                     "media_hosts":hosts,
                     "writes_to_destinations":False}

def write_private(path,body):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.exists():raise ValueError("Refusing to overwrite an existing preparation file")
    data=json.dumps(body,indent=2,ensure_ascii=False).encode()+b"\n"
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as out:out.write(data)
    return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args()
    source_bytes=args.source.read_bytes()
    source=json.loads(source_bytes)
    selected,report=prepare(source)
    target=args.output_dir.resolve()
    if target==args.source.parent.resolve():
        raise ValueError("Use a new output directory to avoid overwriting source")
    if target.exists() and any(target.iterdir()):
        raise ValueError("Output directory must be empty")
    target.mkdir(mode=0o700,parents=True,exist_ok=True)
    source_hash=hashlib.sha256(source_bytes).hexdigest()
    report["full_source_sha256"]=source_hash
    report["selected_media_source_sha256"]=write_private(target/"pilot-media-source.json",selected)
    write_private(target/"pilot-media-inventory.json",report)
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
