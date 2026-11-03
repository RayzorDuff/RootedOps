#!/usr/bin/env python3
"""Create one WC REST key in staging Woo and store Basic auth in private .env.

Refuses preexisting key/authorization. Does not enable any sync flags, change
Woo products or modify unrelated configuration. Run only on RootedOps host.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "dank-store-test-dank-wordpress-1"

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env",type=Path,default=ROOT/".env")
    args=p.parse_args()
    path=args.env.resolve(strict=True)
    if ROOT/".env" != args.env and path != (ROOT/".env").resolve(strict=True):
        p.error("Only the RootedOps runtime .env is supported")
    if not path.is_file() or path.is_symlink():
        p.error("Invalid private environment target")
    if path.stat().st_mode & 0o077:
        p.error("Private .env must have permissions 0600 or stricter")
    lines=path.read_text().splitlines(keepends=True)
    fields={}
    for i,line in enumerate(lines):
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key,val=line.split("=",1)
            fields.setdefault(key.strip(),[]).append((i,val.strip()))
    key="MP_SYNC_WOO_AUTHORIZATION"
    if len(fields.get(key,[]))!=1 or fields[key][0][1].strip("\"'"):
        p.error("Missing or already-populated MP_SYNC_WOO_AUTHORIZATION; refusing replacement")
    if fields.get("MP_SYNC_WOO_ENABLED", [(None,"")])[0][1].lower()!="false":
        p.error("MP_SYNC_WOO_ENABLED must remain false")
    if fields.get("MP_SYNC_WOO_BASE_URL",[(None,"")])[0][1].strip("\"'")!="https://shop-test.danks.store":
        p.error("Expected exact shop-test.danks.store URL")
    inspect=subprocess.run(["sudo","docker","inspect",NAME,
        "--format","{{.State.Running}} {{index .Config.Labels \"com.docker.compose.project\"}}"],
        check=True,capture_output=True,text=True)
    if inspect.stdout.strip()!="true dank-store-test":
        p.error("Unexpected Docker container or project; no keys created")
    proc=subprocess.run(["sudo","docker","exec","-i",NAME,"php","/dev/stdin"],
        input=(ROOT/"scripts/commerce_woo_create_key.php").read_bytes(),
        capture_output=True,check=False)
    if proc.returncode:
        sys.stderr.write(proc.stderr.decode(errors="replace")[-1200:])
        sys.exit("STOP: key provisioning failed; .env unchanged")
    try:
        obj=json.loads(proc.stdout)
        consumer=obj["consumer_key"]
        secret=obj["consumer_secret"]
        assert re.fullmatch(r"ck_[a-f0-9]{40}",consumer)
        assert re.fullmatch(r"cs_[a-f0-9]{40}",secret)
    except Exception:
        sys.exit("STOP: key created but output not recognized. Preserve Woo key and reconcile manually.")
    auth="Basic "+base64.b64encode((consumer+":"+secret).encode()).decode()
    before=path.read_bytes()
    if before!=("".join(lines)).encode():
        sys.exit("STOP: .env changed during provisioning; do not create another key")
    line_number,_=fields[key][0]
    lines[line_number]=key+"="+auth+"\n"
    fd,tmp=tempfile.mkstemp(prefix=".commerce-env-",dir=path.parent)
    try:
        os.fchmod(fd,stat.S_IMODE(path.stat().st_mode))
        with os.fdopen(fd,"wb") as f:
            f.write("".join(lines).encode())
            f.flush()
            os.fsync(f.fileno())
        if path.read_bytes()!=before:
            sys.exit("STOP: .env changed during write; preserve new Woo key and reconcile")
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print("PASS: scoped Woo REST key generated and Basic auth stored in private .env")
    print("Woo API key ID:",obj["key_id"])
    print("MP_SYNC_WOO_ENABLED remains false; no sync or product write executed")
if __name__=="__main__":main()
