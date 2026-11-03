#!/usr/bin/env python3
"""Compile approved Ecwid pilot source and uploaded-media receipts into immutable
five-product draft batches. Offline only: no destination requests/writes.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"integrations/commerce"))
sys.path.insert(0,str(ROOT/"scripts"))
from ecwid_migrate import private_write
from reviewed_catalog import compile_catalog
from commerce_catalog_batch import records_for_batch
from commerce_full_catalog_preflight import APPROVED_PILOT_IDS

SOURCE_FILE_SHA="0b4eec40a1cfd1d62551e2ac951a42dac21984f34ffb2d03f9aea697d1d713a8"
MANIFEST_SHA="447302ab4fda29297d4c3e12060d2546ba529432997c0f9e6445239ba445c46f"
CATEGORIES={"160254004":16,"160255005":17,"160277251":18}


def compile_batches(source,plan,review,media):
    if str(source.get("store_id"))!="95802503" or len(source["products"])!=132:
        raise ValueError("Full source identity/count changed")
    if {int(p["mapping"]["external_product_id"]) for p in plan["products"]}!=APPROVED_PILOT_IDS:
        raise ValueError("Exact original 22-product pilot required")
    if plan["errors"] or review["source_sha256"]!=plan["source_sha256"]:
        raise ValueError("Planner/review digest drift")
    if (review.get("currency"),review.get("currency_confirmed"),
        review.get("selling_price_list"),review.get("draft_only"),
        review.get("defer_tax_mapping"))!=("USD",True,"Standard Selling",True,True):
        raise ValueError("Reviewed production draft, currency, price-list or tax policy drift")
    if {k:v["woocommerce_id"] for k,v in review["categories"].items()}!=CATEGORIES:
        raise ValueError("Destination category mapping drift")
    originals={int(p["id"]):p for p in source["products"]}
    for r in plan["products"]:
        sid=int(r["mapping"]["external_product_id"])
        if originals[sid].get("enabled") is not True or r.get("source_enabled") is not True:
            raise ValueError("Pilot source status drift")
        if r["item"].get("has_variants") or r["item"].get("parent_sku"):
            raise ValueError("Pilot must have only simple products")
        if r["content"]["item"] not in review["items"]:
            raise ValueError("Unreviewed ERP item mapping")
    by_url={}
    for row in media:
        url=row["url"]
        if url in by_url:raise ValueError("Duplicate uploaded URL")
        if not (row.get("erp_file_url","").startswith("/files/") and
                type(row.get("woocommerce_media_id")) is int and row["woocommerce_media_id"]>0):
            raise ValueError("Missing destination media identity")
        by_url[url]=row
    if len(by_url)!=37 or len({v["sha256"] for v in media})!=11:
        raise ValueError("Unexpected verified media coverage")
    expected={img["source_url"] for r in plan["products"] for img in r["content"]["gallery"]}
    if expected!=set(by_url):
        raise ValueError("Uploaded media URLs differ from source plan")
    selected=deepcopy(plan)
    # The test2 pilot proved 37 associations from 11 binaries. Avoid
    # duplicate identical images inside one product gallery, but retain
    # original source references and full Ecwid payload.
    for p in selected["products"]:
        seen=set()
        unique=[]
        for image in p["content"]["gallery"]:
            sha=by_url[image["source_url"]]["sha256"]
            if sha in seen:continue
            seen.add(sha)
            unique.append(image)
        p["content"]["gallery"]=unique
    result=compile_catalog(selected,review,media)
    if len(result["records"])!=22:raise ValueError("Compiled product count drift")
    records=sorted(result["records"],key=lambda p:int(p["mapping"]["external_product_id"]))
    batches=[]
    for start in range(0,22,5):
        document={**result,"records":records[start:start+5]}
        checked=records_for_batch(document)
        assert all(r["woocommerce"]["status"]=="draft" and
                   r["woocommerce"]["stock_quantity"]==0 and
                   r["woocommerce"]["backorders"]=="no" for r in checked)
        batches.append(document)
    return batches


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--full-source",type=Path,required=True)
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--review",type=Path,required=True)
    p.add_argument("--uploaded-media",type=Path,required=True)
    p.add_argument("--upload-manifest",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    args=p.parse_args()
    if hashlib.sha256(args.full_source.read_bytes()).hexdigest()!=SOURCE_FILE_SHA:
        raise ValueError("Full Ecwid source file hash drift")
    if hashlib.sha256(args.upload_manifest.read_bytes()).hexdigest()!=MANIFEST_SHA:
        raise ValueError("Archived upload manifest hash drift")
    media=json.loads(args.uploaded_media.read_text())
    manifest=json.loads(args.upload_manifest.read_text())
    if {r["url"]:r["sha256"] for r in media}!={r["url"]:r["sha256"] for r in manifest}:
        raise ValueError("Uploaded media/archive identity drift")
    batches=compile_batches(json.loads(args.full_source.read_text()),
                             json.loads(args.plan.read_text()),
                             json.loads(args.review.read_text()),media)
    out=args.output_dir
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output directory is not empty: refuse overwrite")
    out.mkdir(mode=0o700,parents=True,exist_ok=True)
    summary=[]
    for i,batch in enumerate(batches,1):
        file=out/f"pilot-{i:02}.json"
        private_write(file,batch)
        sha=hashlib.sha256(file.read_bytes()).hexdigest()
        summary.append({"batch":i,"count":len(batch["records"]),
                        "sha256":sha,"path":str(file),
                        "ecwid_ids":[r["mapping"]["external_product_id"] for r in batch["records"]]})
    private_write(out/"batch-index.json",summary)
    print(json.dumps({"batches":summary,"destination_writes":False},indent=2))


if __name__=="__main__":
    main()
