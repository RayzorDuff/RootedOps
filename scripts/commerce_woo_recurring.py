#!/usr/bin/env python3
"""Guarded recurring MP -> Woo hidden-draft inventory adapter.

One host-local writer. Persistent SQLite high-watermark and write-ahead
attempt journal; never auto-retries an uncertain Woo PUT. Existing production
n8n Woo writer MUST remain disabled. No ERP Stock Ledger or Ecwid writes.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

from commerce_woo_initial_stock import (
    SHOP, approved_woo_ids, owned_product, private_env, source,
)
from commerce_mp_reverse_link import EXPECTED
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = Path.home()/"commerce-migration/inventory-private/woo-recurring-state.sqlite3"
DEFAULT_RECEIPT = Path.home()/"commerce-migration/inventory-private/woo-stock-comparison-24.csv"

def now():
    return datetime.now(timezone.utc).isoformat()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))

def fingerprint(row):
    return hashlib.sha256(canonical(row).encode()).hexdigest()

def settings():
    path = ROOT/".env"
    opts = {}
    for line in path.read_text().splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            k,v = line.split("=",1)
            if k in opts: raise ValueError("Duplicate .env key "+k)
            opts[k] = v.strip().strip('"').strip("'")
    if opts.get("MP_SYNC_WOO_ENABLED","").lower() != "false":
        raise ValueError("STOP: n8n Woo writer must remain disabled")
    if opts.get("MP_SYNC_WOO_BASE_URL") != SHOP:
        raise ValueError("Unexpected Woo origin")
    return opts

@contextmanager
def locked(db_path):
    # Files live only in private host inventory directory; lock never follows symlinks.
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if db_path.is_symlink(): raise ValueError("State database cannot be symlink")
    lock_path = db_path.with_name(db_path.name+".lock")
    fd = os.open(lock_path, os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)

def connect(db_path, create=False):
    if db_path.is_symlink(): raise ValueError("State path symlink refused")
    if not create and not db_path.is_file():
        raise ValueError("State missing: bootstrap after verifying initial projection")
    db = sqlite3.connect(str(db_path), timeout=3, isolation_level=None)
    db.execute("PRAGMA busy_timeout=3000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("""CREATE TABLE IF NOT EXISTS projection(
        mp_id INTEGER PRIMARY KEY, woo_id INTEGER UNIQUE NOT NULL,
        sku TEXT NOT NULL, last_qty INTEGER NOT NULL,
        source_hash TEXT NOT NULL, revision INTEGER NOT NULL,
        acked_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS attempts(
        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
        mp_id INTEGER NOT NULL, woo_id INTEGER NOT NULL,
        revision INTEGER NOT NULL, source_hash TEXT NOT NULL,
        before_qty INTEGER NOT NULL, target_qty INTEGER NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','verified','failed')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        error TEXT,
        UNIQUE(mp_id,revision))""")
    return db

def rowset(identity_receipt, auth):
    rows=source()
    ids=approved_woo_ids(identity_receipt)
    if len(rows)!=24 or len(ids)!=24:raise ValueError("Expected 24 approved mappings")
    woo={}
    for row in rows:
        mid=row["mp_id"]
        p=owned_product(ids[mid], row, auth)
        woo[mid]={"id":ids[mid],"qty":p["stock_quantity"],"row":row}
    return rows, woo

def state_map(db):
    return {int(r[0]):dict(mp_id=r[0],woo_id=r[1],sku=r[2],last_qty=r[3],
                          source_hash=r[4],revision=r[5])
            for r in db.execute("SELECT mp_id,woo_id,sku,last_qty,source_hash,revision FROM projection")}

def pending(db):
    return db.execute("SELECT COUNT(*) FROM attempts WHERE status!='verified'").fetchone()[0]

def bootstrap(db, rows, woo):
    if db.execute("SELECT COUNT(*) FROM projection").fetchone()[0] or db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]:
        raise ValueError("Existing state/attempts: bootstrap is not repeatable")
    if any(woo[r["mp_id"]]["qty"] != r["qty"] for r in rows):
        raise ValueError("Woo does not equal MP: reconcile before initializing state")
    ts=now()
    db.execute("BEGIN IMMEDIATE")
    try:
        for r in rows:
            db.execute("INSERT INTO projection VALUES(?,?,?,?,?,?,?)",
                       (r["mp_id"],woo[r["mp_id"]]["id"],r["sku"],r["qty"],
                        fingerprint(r),1,ts))
        db.commit()
    except Exception:
        db.rollback()
        raise
    print("BOOTSTRAPPED: 24 MP/Woo matching stocks, revision 1, no Woo writes")

def preview(db,rows,woo):
    states=state_map(db)
    if len(states)!=24 or pending(db):
        raise ValueError("State incomplete or unresolved attempt: manual reconciliation required")
    changed=[]
    for r in rows:
        mid=r["mp_id"]
        s=states[mid]
        w=woo[mid]
        if s["woo_id"]!=w["id"] or s["sku"]!=r["sku"]:
            raise ValueError("Reviewed Woo identity drift")
        if w["qty"] != s["last_qty"]:
            raise ValueError("Woo target diverged from durable acknowledgment for "+r["sku"])
        if r["qty"]!=s["last_qty"]:
            changed.append((r,s,w))
    print("PREVIEW: 24 approved hidden drafts, pending quantity changes:",len(changed))
    for r,s,w in changed:
        print(r["sku"],"Woo",w["id"],s["last_qty"],"->",r["qty"],
              "next revision",s["revision"]+1)
    return changed

def one_write(db,r,s,w,auth,identity_receipt):
    # Fresh complete source read before *each* change limits obsolete writes.
    latest=source()
    current={a["mp_id"]:a for a in latest}
    if current[r["mp_id"]]!=r:
        raise ValueError("MP source changed since run began; stop and retry with fresh snapshot")
    # The full source set must not drift midrun: another row's inventory may
    # share a stock admission path even if the 24 mapped pools are distinct.
    if latest!=one_write.snapshot:
        raise ValueError("MP source snapshot drift during projection")
    product=owned_product(w["id"],r,auth)
    if product["stock_quantity"]!=s["last_qty"]:
        raise ValueError("Woo changed since previous ACK; refuse overwrite")
    ts=now()
    revision=s["revision"]+1
    h=fingerprint(r)
    db.execute("INSERT INTO attempts(mp_id,woo_id,revision,source_hash,before_qty,target_qty,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (r["mp_id"],w["id"],revision,h,s["last_qty"],r["qty"],"pending",ts,ts))
    # Pending is committed to disk before network request. On a crash,
    # subsequent runs stop rather than replay the unknown outcome.
    from ecwid_migrate import api\n    def put_stock(shop, id, quantity, authorization):\n        response=api(shop+'/wp-json/wc/v3/products/'+str(id),authorization,'PUT',{'stock_quantity':quantity})\n        if response.get('id')!=id: raise ValueError('Woo product ID changed during PUT')
    try:
        put_stock(SHOP,w["id"],r["qty"],auth)
        after=owned_product(w["id"],r,auth)
        if after["stock_quantity"]!=r["qty"]:
            raise ValueError("Woo read-back does not match requested stock")
    except Exception as ex:
        db.execute("UPDATE attempts SET status='failed',updated_at=?,error=? WHERE mp_id=? AND revision=?",
                   (now(),str(ex)[:500],r["mp_id"],revision))
        raise
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("UPDATE projection SET last_qty=?,source_hash=?,revision=?,acked_at=? WHERE mp_id=? AND revision=?",
                   (r["qty"],h,revision,now(),r["mp_id"],s["revision"]))
        if db.execute("SELECT changes()").fetchone()[0]!=1:
            raise ValueError("Concurrent state revision drift")
        db.execute("UPDATE attempts SET status='verified',updated_at=? WHERE mp_id=? AND revision=?",
                   (now(),r["mp_id"],revision))
        db.commit()
    except Exception:
        db.rollback()
        raise
    print("VERIFIED:",r["sku"],"Woo",w["id"],r["qty"],"revision",revision)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=["check","bootstrap","apply"])
    p.add_argument("--state",type=Path,default=DEFAULT_STATE)
    p.add_argument("--identity-receipt",type=Path,default=DEFAULT_RECEIPT)
    args=p.parse_args()
    os.umask(0o077)
    opts=settings()
    if args.mode=="apply" and opts.get("MP_WOO_RECURRING_CLI_ENABLED","false").lower()!="true":
        raise ValueError("Apply disabled: MP_WOO_RECURRING_CLI_ENABLED=true required")
    with locked(args.state):
        auth=private_env()
        db=connect(args.state, create=args.mode=="bootstrap")
        try:
            rows,woo=rowset(args.identity_receipt,auth)
            if args.mode=="bootstrap":
                bootstrap(db,rows,woo)
                return
            changed=preview(db,rows,woo)
            if args.mode=="check":
                print("READ ONLY: no Woo writes")
                return
            one_write.snapshot=rows
            for r,s,w in changed:one_write(db,r,s,w,auth,args.identity_receipt)
            print("COMPLETE: all attempted updates verified; n8n Woo branch remains disabled")
        finally:
            db.close()

if __name__=="__main__": main()
