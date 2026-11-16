#!/usr/bin/env bash
# Configure the Dank Woo signup integration on the production Frappe site.
set -euo pipefail

backend=erpnext-backend
site=erp.danks.store
sites=/home/frappe/frappe-bench/sites
python=/home/frappe/frappe-bench/env/bin/python
mode=setup
case "${1:-}" in
  "") ;;
  --enable-projection) mode=enable ;;
  --disable-projection) mode=disable ;;
  *) printf 'Usage: %s [--enable-projection|--disable-projection]\n' "$0" >&2; exit 2 ;;
esac
sudo -v

configure() {
  sudo docker exec -i --user frappe --workdir "$sites" "$backend" "$python" -c '
import base64
import json
import os
from pathlib import Path
import re
import sys
import tempfile

path = Path(sys.argv[1]) / "site_config.json"
mode = sys.argv[2]
config = json.loads(path.read_text())
settings = config.setdefault("commerce_customer_sync", {})
if not isinstance(settings, dict):
    raise SystemExit("Expected commerce_customer_sync to be a JSON object. No changes made.")
if settings.get("woo_site") not in (None, "shop-test.danks.store"):
    raise SystemExit("Existing customer integration points to another shop. No changes made.")

if mode == "setup":
    key = sys.stdin.readline().strip()
    secret = sys.stdin.readline().strip()
    if not re.fullmatch(r"ck_[a-fA-F0-9]{40}", key) or not re.fullmatch(r"cs_[a-fA-F0-9]{40}", secret):
        raise SystemExit("Expected a Woo Consumer Key and Consumer Secret. No changes made.")
    settings.setdefault("woo_customer_ids", [])
    settings.setdefault("customer_group", "Individual")
    settings.setdefault("territory", "United States")
    settings.setdefault("project_enabled", False)
    settings.update(
        enabled=True,
        production_erp_pilot=True,
        provision_new_woo_customers=True,
        woo_site="shop-test.danks.store",
        woo_authorization="Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode(),
    )
else:
    if (settings.get("production_erp_pilot") is not True
            or settings.get("woo_site") != "shop-test.danks.store"):
        raise SystemExit("Configure the shop-test pairing before changing projection. No changes made.")
    if mode == "enable" and (not settings.get("enabled") or not settings.get("woo_authorization")):
        raise SystemExit("Enable customer sync and set a Woo credential first. No changes made.")
    settings["project_enabled"] = mode == "enable"

with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
    temporary = Path(stream.name)
    try:
        json.dump(config, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

if mode == "setup":
    print("Woo signup provisioning configured on " + sys.argv[1])
else:
    print("Scheduled ERP-to-Woo projection " + ("enabled" if settings["project_enabled"] else "disabled"))
' "$site" "$mode"
}

if [[ "$mode" != setup ]]; then
  configure </dev/null
elif [[ -t 0 ]]; then
  read -rs -p 'Woo Consumer Key: ' woo_key
  printf '\n'
  read -rs -p 'Woo Consumer Secret: ' woo_secret
  printf '\n'
  printf '%s\n' "$woo_key" "$woo_secret" | configure
  unset woo_key woo_secret
else
  # A private input stream contains the consumer key and secret on separate lines.
  configure
fi

sudo docker exec "$backend" bench --site "$site" clear-cache
