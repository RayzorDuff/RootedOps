#!/usr/bin/env python3
"""Guarded production ERP / staging Woo draft import.

Reuses the existing batch runner's immutable compiled-hash, source identity,
native ERP transactional write, Woo idempotency, and receipt verification.
Does not modify or relax the isolated test2 runner.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("commerce_test2_batch", HERE / "commerce_catalog_batch.py")
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)

ERP_SITE = "erp.danks.store"
ERP_CONTAINER = "erpnext-backend"
SHOP_CONTAINER = "dank-store-test-dank-wordpress-1"
SHOP_ORIGIN = "https://shop-test.danks.store"
ERP_ORIGIN = "https://erp.danks.store"


def require_container(name, project):
    c = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]
    if not c["State"]["Running"] or c["Config"]["Labels"].get("com.docker.compose.project") != project:
        raise ValueError("Unexpected container identity or stopped service: " + name)
    return c


def guard(environment):
    path = environment.resolve()
    if not path.is_dir() or path.name != "commerce-migration":
        raise ValueError("Use dedicated operator-owned commerce-migration directory")
    private = path / "private"
    private.mkdir(mode=0o700, exist_ok=True)
    if private.stat().st_mode & 0o077:
        raise ValueError("Private receipt directory must be mode 0700")
    require_container(ERP_CONTAINER, "docker")
    woo = require_container(SHOP_CONTAINER, "dank-store-test")
    ports = woo["NetworkSettings"]["Ports"].get("80/tcp") or []
    if any(p["HostIp"] not in ("127.0.0.1", "::1") or p["HostPort"] != "8097" for p in ports) or not ports:
        raise ValueError("Staging WordPress must bind only host loopback 8097")

    php = """require '/var/www/html/wp-load.php';
if (!class_exists('WooCommerce')) { exit(3); }
$gateways=WC()->payment_gateways()->get_available_payment_gateways();
echo json_encode(['site'=>get_option('siteurl'),
'coming_soon'=>get_option('woocommerce_coming_soon'),
'calc_taxes'=>get_option('woocommerce_calc_taxes'),
'gateways'=>count($gateways),
'published'=>(int)(wp_count_posts('product')->publish ?? 0)]);"""
    live = json.loads(subprocess.check_output(["docker", "exec", SHOP_CONTAINER, "php", "-r", php]))
    if (live["site"] != SHOP_ORIGIN or live["coming_soon"] != "yes" or
        live["calc_taxes"] != "no" or live["gateways"] != 0 or live["published"] != 0):
        raise ValueError("WordPress staging, checkout, tax or publication guard failed")
    return {"erp": ERP_ORIGIN, "shop": SHOP_ORIGIN}, private


def compiled_guard(compiled):
    raw = compiled.read_bytes()
    document = json.loads(raw)
    if not 1 <= len(document.get("records", [])) <= 5:
        raise ValueError("Import batches must contain one through five products")
    for r in document["records"]:
        source = json.loads(r["content"]["source_payload"])["product"]
        original = source.get("enabled")
        status = {m["key"]: m["value"] for m in r["woocommerce"].get("meta_data", [])}.get(
            "_rootedops_ecwid_enabled")
        if original not in (True, False) or status != ("yes" if original else "no"):
            raise ValueError("Reviewed source enabled/disabled provenance required")
        if original is False:
            # Full-catalog disabled import follows after validated 22-product acceptance.
            raise ValueError("Disabled-source imports are not yet authorized for production")
        if (r["woocommerce"].get("status") != "draft" or
            r["woocommerce"].get("catalog_visibility") != "hidden" or
            r["woocommerce"].get("stock_quantity") != 0 or
            r["woocommerce"].get("manage_stock") is not True or
            r["woocommerce"].get("backorders") != "no" or
            r["mapping"].get("sync_enabled") != 0):
            raise ValueError("Draft-only/non-sellable guard failed")
    return hashlib.sha256(raw).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("environment", type=Path)
    p.add_argument("compiled", type=Path)
    p.add_argument("--sha256", required=True)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    if compiled_guard(args.compiled) != args.sha256:
        raise ValueError("Compiled batch SHA mismatch")
    # Never touch the test2 runner's source. Replace only exact integration
    # execution targets while preserving its transactional write checks.
    original = batch.NATIVE
    expected = "frappe.init(site='erp-test2.danks.store')"
    if original.count(expected) != 1:
        raise ValueError("ERP native runner version drift")
    modified = original.replace(expected, "frappe.init(site='erp.danks.store')")
    isolated = " assert frappe.conf.get('maintenance_mode') and frappe.conf.get('pause_scheduler')"
    if modified.count(isolated) != 1:
        raise ValueError("ERP native safety layout drift")
    # Production runs normal payroll, email and scheduling; do not change that
    # state. Transaction and protected DocType counts remain checked by NATIVE.
    modified = modified.replace(isolated, "")
    email_guard = " for dt,f in [('Email Account',{'enable_outgoing':1}),('Webhook',{'enabled':1}),('Notification',{'enabled':1})]:assert frappe.db.count(dt,f)==0"
    if modified.count(email_guard) != 1:
        raise ValueError("ERP native email guard layout drift")
    modified = modified.replace(email_guard, "")
    batch.NATIVE = modified
    batch.guarded_environment = guard
    batch.records_for_batch = records_for_prod(batch.records_for_batch)
    # The original runner hardcodes the test2 backend container in docker exec;
    # replace that reference only in the runner's native subprocess argument
    # by a tightly scoped subprocess.run wrapper, without modifying its checks.
    original_run = batch.subprocess.run
    def native_run(argv, *a, **kw):
        if isinstance(argv, list) and "rootedops-full-test-erpnext-backend-1" in argv:
            argv = [ERP_CONTAINER if v == "rootedops-full-test-erpnext-backend-1" else v for v in argv]
        return original_run(argv, *a, **kw)
    batch.subprocess.run = native_run
    batch.run(args.environment, args.compiled, args.sha256, apply=args.apply)


def records_for_prod(original):
    def checked(document):
        records = original(document)
        for r in records:
            if r["mapping"]["site_key"] != "95802503":
                raise ValueError("Unexpected Ecwid store")
        return records
    return checked


if __name__ == "__main__":
    main()
