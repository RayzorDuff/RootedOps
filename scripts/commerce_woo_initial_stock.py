#!/usr/bin/env python3
"""Guarded one-time initial MP -> existing WooCommerce *hidden drafts* stock projection.

plan: live MP snapshot + Woo GET identity/current stock, private immutable plan.
apply: explicit approved plan digest, fresh MP identical source, Woo exact
before-value compare, journal before first PUT and each verified result.
Never activates recurring sync, changes status or touches Ecwid/ERP stock ledger.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"integrations/commerce"))
from ecwid_migrate import api
from staging_origin import staging_origin
from commerce_mp_reverse_link import EXPECTED

FIELDS=("ecommerce_id","erp_item_code","external_sku","external_product_id",
        "external_variation_id","provider","site_key","physical_quantity","projected_quantity")
EXPECTED_SKUS={str(mp):(sku,ecwid) for mp,sku,ecwid in EXPECTED}
SHOP="https://shop-test.danks.store"

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True)

def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def private_env():
    path=ROOT/".env"
    values={}
    for line in path.read_text().splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            k,v=line.split("=",1)
            if k in values: raise ValueError("Duplicate private environment key "+k)
            values[k]=v.strip().strip('"').strip("'")
    if values.get("MP_SYNC_WOO_ENABLED","").lower()!="false":
        raise ValueError("Automated Woo switch must be false")
    if values.get("MP_SYNC_WOO_BASE_URL")!=SHOP:
        raise ValueError("Wrong Woo target URL")
    auth=values.get("MP_SYNC_WOO_AUTHORIZATION","")
    if not auth.startswith("Basic "): raise ValueError("Run auth provisioning first")
    return auth

def source():
    sql=(ROOT/"scripts/commerce_mp_inventory_csv.sql").read_text()
    command=["sudo","docker","exec","-i","mushroomprocess-bridge-postgres",
             "sh","-c",'PGPASSWORD="$POSTGRES_PASSWORD" exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
    p=subprocess.run(command,input=sql,text=True,capture_output=True,check=True)
    rows=list(csv.DictReader(io.StringIO(p.stdout)))
    if not rows or tuple(rows[0])!=FIELDS: raise ValueError("Unexpected MP CSV schema")
    if len(rows)!=24 or {r["ecommerce_id"] for r in rows}!=set(EXPECTED_SKUS):
        raise ValueError("Refusing incomplete/duplicate MP inventory snapshot")
    result=[]
    for r in rows:
        mp=r["ecommerce_id"]
        sku,ecwid=EXPECTED_SKUS[mp]
        if (r["erp_item_code"]!=sku or r["external_sku"]!=sku
                or r["external_product_id"]!=ecwid or r["external_variation_id"]
                or r["provider"]!="ecwid" or r["site_key"]!="dank_mushrooms"):
            raise ValueError("MP source identity drift "+mp)
        physical=int(r["physical_quantity"])
        qty=int(r["projected_quantity"])
        if not 0<=qty<=physical:raise ValueError("Invalid MP available quantity "+mp)
        result.append(dict(mp_id=int(mp),sku=sku,ecwid_id=ecwid,physical=physical,qty=qty))
    return sorted(result,key=lambda x:x["mp_id"])

def approved_woo_ids(path):
    with path.open(newline="") as f:rows=list(csv.DictReader(f))
    if len(rows)!=24 or {r["ecommerce_id"] for r in rows}!=set(EXPECTED_SKUS):
        raise ValueError("Approved Woo identity receipt must cover exactly 24 MP IDs")
    mapped={}
    ids=set()
    for r in rows:
        mp=r["ecommerce_id"]
        sku,ecwid=EXPECTED_SKUS[mp]
        wid=int(r["woo_id"])
        if (r["status"]!="MATCHED" or r["erp_item"]!=sku
                or r["ecwid_product_id"]!=ecwid or wid<=0 or wid in ids):
            raise ValueError("Unapproved Woo identity receipt row "+mp)
        ids.add(wid)
        mapped[int(mp)]=wid
    return mapped

def owned_product(id,src,auth):
    product=api(SHOP+"/wp-json/wc/v3/products/"+str(id)+"?context=edit",auth)
    def meta(key):
        values=[m.get("value") for m in product.get("meta_data",[]) if m.get("key")==key]
        if len(values)>1:raise ValueError("Duplicate Woo marker "+key)
        return str(values[0]) if values else ""
    expected="ecwid:95802503:product:"+src["ecwid_id"]
    if (product.get("id")!=id or product.get("sku")!=src["sku"]
        or meta("_rootedops_source_key")!=expected
        or meta("_rootedops_erp_item") not in ("",src["sku"])
        or product.get("type")!="simple" or product.get("status")!="draft"
        or product.get("catalog_visibility")!="hidden"
        or product.get("manage_stock") is not True
        or type(product.get("stock_quantity")) is not int):
        raise ValueError("Woo identity/stock guard failed for "+src["sku"])
    return product

def private_create(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,"w") as f:
        f.write(canonical(value)+"\n")
        f.flush()
        os.fsync(f.fileno())

def note(handle,value):
    handle.write(canonical(value)+"\n")
    handle.flush()
    os.fsync(handle.fileno())

def plan(args,auth):
    if args.file.exists():raise ValueError("Plan already exists; preserve previous receipt")
    src=source()
    ids=approved_woo_ids(args.identity_receipt)
    rows=[]
    for r in src:
        id=ids[r["mp_id"]]
        woo=owned_product(id,r,auth)
        before=woo["stock_quantity"]
        rows.append(dict(r,woo_id=id,before=before))
    changes=[r for r in rows if r["before"]!=r["qty"]]
    # Only the 7 exact previously approved draft IDs may be changed on initial push.
    approved_initial={25,35,38,40,43,44,45}
    if {r["woo_id"] for r in changes}!=approved_initial:
        raise ValueError("Initial delta set differs from reviewed 7 Woo IDs")
    if any(r["before"]!=0 for r in changes):
        raise ValueError("Initial updates must start from zero")
    data={"schema":1,"target":SHOP,"rows":rows,"source_hash":sha(src),
          "created_utc":datetime.now(timezone.utc).isoformat()}
    data["approval_digest"]=sha(data)
    private_create(args.file,data)
    print("PREVIEW: 24/24 exact Woo draft identities; changes:",len(changes))
    for r in changes:print("Woo",r["woo_id"],r["sku"],r["before"],"->",r["qty"])
    print("Plan:",args.file)
    print("Approval digest:",data["approval_digest"])
    print("NO WRITES")

def apply(args,auth):
    data=json.loads(args.file.read_text())
    stored=data.get("approval_digest")
    without={k:v for k,v in data.items() if k!="approval_digest"}
    if (data.get("schema")!=1 or data.get("target")!=SHOP
        or stored!=sha(without) or args.approve!=stored):
        raise ValueError("Invalid or unapproved plan")
    current_source=source()
    if sha(current_source)!=data["source_hash"]:
        raise ValueError("MP inventory changed since preview: regenerate plan")
    if len(data["rows"])!=24 or [r["mp_id"] for r in data["rows"]]!=[r["mp_id"] for r in current_source]:
        raise ValueError("Incomplete/out-of-order approval plan")
    ids=approved_woo_ids(args.identity_receipt)
    approved_initial={25,35,38,40,43,44,45}
    changes=[]
    for row,src in zip(data["rows"],current_source):
        if {k:row[k] for k in ("mp_id","sku","ecwid_id","physical","qty")}!=src:
            raise ValueError("MP identity/quantity drift")
        if row["woo_id"]!=ids[row["mp_id"]]:
            raise ValueError("Woo ID drift")
        p=owned_product(row["woo_id"],row,auth)
        if p["stock_quantity"]!=row["before"]:
            raise ValueError("Woo quantity changed since preview "+row["sku"])
        if row["before"]!=row["qty"]: changes.append(row)
    if {r["woo_id"] for r in changes}!=approved_initial:
        raise ValueError("Changed target set does not equal approved seven")
    if any(r["before"]!=0 for r in changes):
        raise ValueError("Unexpected initial stock before state")
    journal=args.file.with_name(args.file.name+".journal.jsonl")
    fd=os.open(journal,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w") as log:
        note(log,{"event":"START","digest":stored,"count":len(changes)})
        for row in changes:
            id=row["woo_id"]
            before=owned_product(id,row,auth)
            if before["stock_quantity"]!=row["before"]:
                raise ValueError("Woo concurrent drift before PUT "+row["sku"])
            note(log,{"event":"ATTEMPT","woo_id":id,"mp_id":row["mp_id"],
                      "expected_before":row["before"],"qty":row["qty"]})
            response=api(SHOP+"/wp-json/wc/v3/products/"+str(id),auth,
                         "PUT",{"stock_quantity":row["qty"]})
            after=owned_product(id,row,auth)
            if response.get("id")!=id or after["stock_quantity"]!=row["qty"]:
                raise ValueError("Woo PUT read-back mismatch "+row["sku"])
            note(log,{"event":"VERIFIED","woo_id":id,"qty":row["qty"]})
        # Verify all 24 ownership/availability records still agree.
        for row in data["rows"]:
            product=owned_product(row["woo_id"],row,auth)
            if product["stock_quantity"]!=row["qty"]:
                raise ValueError("Final read-back drift "+row["sku"])
        note(log,{"event":"COMPLETE","count":len(changes),"digest":stored})
    print("APPLIED:",len(changes),"draft stock updates; all 24 read back")
    print("Private journal:",journal)
    print("Ecwid, ERP Stock Ledger and recurring Woo sync unchanged")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",choices=("plan","apply"),required=True)
    p.add_argument("--file",type=Path,required=True)
    p.add_argument("--identity-receipt",type=Path,default=Path.home()/"commerce-migration/inventory-private/woo-stock-comparison-24.csv")
    p.add_argument("--approve",help="Exact preview digest, required for apply")
    args=p.parse_args()
    os.umask(0o077)
    if args.mode=="apply" and not args.approve:p.error("--approve required")
    auth=private_env()
    if args.mode=="plan":plan(args,auth)
    else:apply(args,auth)

if __name__=="__main__":
    main()
