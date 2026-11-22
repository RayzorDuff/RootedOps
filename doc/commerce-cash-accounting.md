# Cash receipt → ERP accounting

This is a separately enabled tender adapter. It does not call Clover, create processor evidence or infer payment from Woo status/MP dispatch. MP 061 records actual cash received with a UUID, immutable source snapshot, amount/currency/time/operator. The trusted worker signs that receipt; ERP requires financial permission, the same private evidence key, exact source approval, reviewed company/customer/items/prices/tax and an enabled company/currency cash/undeposited-funds account.

Ecwid cash orders can create one reviewed native Sales Order, invoice and Payment Entry without requiring the unfinished Woo stack in MP. Woo cash orders reuse their already submitted Sales Order from authenticated intake. Registered buyer links and guest mappings stay in that intake; cash posting creates no Customers. A completed historical cash web order is not copied to Woo or dispatched again. First check for existing invoices/payments; partial or different existing links require review.

Native Frappe creates/submits invoice and payment in one request transaction; a payment write failure rolls the invoice/sale back. A lost response retries the same receipt and returns the same references. The invoice is stock-neutral (`update_stock=0`); MP owns physical stock and dispatch. Existing financial-link uniqueness is reused. Tax, line totals, shipping and company/currency drift fail closed. A refund/split tender, a cancelled source, changed financial snapshot or unresolved account remains review, with the original cash receipt retained. Refund and physical return are separate actions.

## Private configuration (owner only)

Copy `config/commerce-cash-worker.example.json` and `config/commerce-cash-erp.example.json` outside Git, chmod 600, and keep posting disabled initially. Do not paste their filled contents into a chat/issue. The worker uses the existing private `COMMERCE_LIVE_MP_DSN` and `ERP_AUTHORIZATION`, plus new `COMMERCE_CASH_EVIDENCE_KEY` (at least 32 random bytes). Use the same key as ERP `evidence_hmac`; it is different from webhook, Clover and n8n operator tokens. Woo projection also uses existing `WOO_MP_AUTHORIZATION`.

Worker approval for each cash UUID contains:

- `enabled: true`, `source_key: "provider|site_key|external_order_id"`, and the `source_fingerprint` from read-only preview.
- For Ecwid: exact ordered `lines` with `line_id`, `source_sku`, `external_product_id`, `erp_item_code`, integer `quantity`. Source item IDs/SKUs and quantities must agree; do not remap an external product to fix a mismatch.
- For Woo: `lines` exactly matching the MP normalized lines, including ecommerce ID. Preserve Woo numeric order/line IDs and the logical store `danks.store`.

ERP `approved_orders` uses that same source key and contains `enabled: true`, `stock_authority: "mushroomprocess"`, `source_fingerprint`, reviewed `posting_date`, `reviewed_draft`, and an approved native destination `tax_quote` for production. The draft is the existing reviewed ERP contract: Customer, company, currency, conversion_rate, transaction/delivery dates, selling_price_list, Item quantities/rates, Actual tax rows, docstatus 0 and ignore_pricing_rule 1. Shipping uses the existing reviewed nonstock `commerce_order_shipping_item`; Woo source line/shipping/tax amounts must agree. Missing tax/account/customer mapping is a stop point, not an assumed zero tax or a new Customer.

Use the earlier order review/quote tooling for native mapping; this adapter does not provide a second tax engine. Configure the new cash account independently of Clover clearing. A bank deposit is subsequently reconciled as transfer of the cash already received, not another sale.

## 1 — inspect receipts (Linode, private worker environment)

Activate the existing reviewed Python environment and load its private systemd environment through the existing operation procedure; do not source an unreviewed file or print it. Set these **paths**, not credentials:

```bash
cd ~/RootedOps
: "${ORDER_PYTHON:?Set the existing worker Python path}"
: "${CASH_ACCOUNTING_CONFIG:?Set the private cash-worker JSON path}"
"$ORDER_PYTHON" integrations/commerce/cash_reconciliation.py list \
  --config "$CASH_ACCOUNTING_CONFIG"
```

Success: UUID, source order, amount/currency and ERP acknowledgment state only. This reads no customer fields and makes no writes. Stop if source identity/database is unexpected. The current cash web sale needs its real MP receipt entered through the authenticated UI first; don't invent a cash UUID or fabricate a Clover capture.

Select the exact UUID and preview it:

```bash
read -r -p 'Reviewed cash receipt UUID: ' CASH_RECEIPT_ID
"$ORDER_PYTHON" integrations/commerce/cash_reconciliation.py preview \
  --config "$CASH_ACCOUNTING_CONFIG" --receipt-id "$CASH_RECEIPT_ID"
```

Success: immutable fingerprint, order and sanitized product/line identifiers and amounts. Review these privately against the actual sale and existing ERP records before adding matching worker/ERP approvals. No posting occurs. Stop on unknown SKU, changed quantities, missing Customer or tax/account uncertainty.

## 2 — prepare ERP config safely (Linode, after verified backup)

The existing production bench is used; no new bench. Deploy/review the rootedops_commerce **0.3.7** candidate through the existing image procedure first (`scripts/erpnext_image_candidate.sh --build` builds a candidate only). Coordinate its actual image rollout/restarts; building is not deployment. Use the existing ERP backup and migrate procedure in the launch runbook.

Set `CASH_PRIVATE_DIR` to the private backup/config directory. `erp-cash.json` is the owner-reviewed patch, initially disabled. This block creates a new config copy, not a production write:

```bash
(
  set -eu
  cd ~/RootedOps
  : "${CASH_PRIVATE_DIR:?Set a private directory containing erp-cash.json}"
  umask 077
  sudo docker cp erpnext-backend:/home/frappe/frappe-bench/sites/erp.danks.store/site_config.json \
    "$CASH_PRIVATE_DIR/site-config.before.json"
  sudo chown "$(id -u):$(id -g)" "$CASH_PRIVATE_DIR/site-config.before.json"
  chmod 600 "$CASH_PRIVATE_DIR/site-config.before.json" "$CASH_PRIVATE_DIR/erp-cash.json"
  python3 scripts/commerce_cash_config.py \
    --site-config "$CASH_PRIVATE_DIR/site-config.before.json" \
    --cash-config "$CASH_PRIVATE_DIR/erp-cash.json" \
    --output "$CASH_PRIVATE_DIR/site-config.cash.json"
)
```

Success: existing ERP settings/credentials are preserved; only the cash configuration is merged into a new mode-600 file. Stop if inputs are not private, the output already exists or required account/key fields are missing when enabling. Review locally; do not paste site_config.json.

Cash posting also requires the existing `commerce_order_integration_enabled=true` ERP flag. Verify it through the existing order preflight; when the reviewed deployment authorizes enabling it, the exact command is `sudo docker exec erpnext-backend bench --site erp.danks.store set-config --parse commerce_order_integration_enabled True`. This does not replace the cash source/account/receipt approvals.

The next block **changes production ERP configuration**. Only run it after owner approval of the candidate/app version, backups and exact account/mappings:

```bash
(
  set -eu
  : "${CASH_PRIVATE_DIR:?Set the reviewed private config directory}"
  sudo docker cp "$CASH_PRIVATE_DIR/site-config.cash.json" \
    erpnext-backend:/home/frappe/frappe-bench/sites/erp.danks.store/site_config.json
  sudo docker exec erpnext-backend sh -ec \
    'chown frappe:frappe /home/frappe/frappe-bench/sites/erp.danks.store/site_config.json; chmod 600 /home/frappe/frappe-bench/sites/erp.danks.store/site_config.json'
  sudo docker exec erpnext-backend bench --site erp.danks.store clear-cache
)
```

Success: clear-cache succeeds. Stop on any error. Retain both private config copies; do not replace newer unrelated ERP settings with a stale copy during rollback. Changes to a persistent worker's environment/config need its coordinated restart through the existing unit procedure, not a blanket Docker restart.

## 3 — explicitly post one reviewed receipt (financial write)

Keep worker `enabled=false` and production orders gated until the synthetic/native tests and hosted preflight pass. Enable only the reviewed receipt/account configuration when ready. Then this command creates/reuses financial documents on the configured ERP. It is not a preview:

```bash
"$ORDER_PYTHON" integrations/commerce/cash_reconciliation.py post \
  --config "$CASH_ACCOUNTING_CONFIG" --receipt-id "$CASH_RECEIPT_ID"
```

Success: `accounted` with Sales Order, Sales Invoice and Payment Entry references, and an MP acknowledgment. Repeat the same UUID to prove identical references. Stop on error or review: inspect current receipts/documents; never replace the UUID or issue an unrelated Payment Entry to bypass a timeout. A failed MP acknowledgment after ERP commit retries the same ERP receipt without duplicate posting.

For Woo, enable `cash_orders_enabled` explicitly in the existing production order config, enable `ROOTEDOPS_MP_CASH_ENABLED` privately in WordPress, and use MP's cash-aware rendered Woo workflow/bundle **after** 054–059 and 061 preparation. Only reviewed Woo COD (`cod`) is supported initially. After posting, the worker writes the same receipt/amount/currency to the authenticated Woo order endpoint. It moves pending/on-hold to processing, not completed, without inventing a transaction ID. Native signed Woo delivery must reach the inbox/MP before confirmation. `awaiting_paid_woo_snapshot_or_review` means ERP is retained but dispatch stays gated; retry after checking delivery. Label purchase still cannot dispatch or complete MP stock.

## 4 — ongoing operation / pause

After hosted acceptance, the existing multiorder worker can use `cash_accounting_config` pointing to the private cash JSON. Its cycle retries enabled, individually reviewed cash UUIDs and retains review outcomes. Alternatively run `cash_reconciliation.py cycle --config "$CASH_ACCOUNTING_CONFIG"` through the reviewed scheduler. Recording cash is always an explicit authenticated operator action. Customer/item/tax/account approvals are reviews, not automated guesses. A single approved UUID is a pilot; add each subsequent reviewed receipt to the ongoing queue. Disable/omit the cash gateway until that operator routine is accepted.

To pause cash posting, merge a private patch `{"enabled":false}` with `scripts/commerce_cash_config.py` and disable the worker cash config `enabled` flag; this preserves secrets, approvals and receipts. Disable `cash_orders_enabled` and `ROOTEDOPS_MP_CASH_ENABLED` if pausing new Woo cash orders/projection. Existing Clover web checkout and Ecwid rollback availability are separate. Reconcile accepted money/orders before changing checkouts or stock ownership. Never restore a pre-sale DB or delete cash receipts. Manual refunds/physical returns remain reviewed reversals in the established native interfaces; automation does not issue them.

## WordPress cash flag — coordinated storefront change

The Git Compose file maps `DANK_MP_CASH_ENABLED=0` by default to `ROOTEDOPS_MP_CASH_ENABLED`. Keep it 0 until approved hosted COD acceptance. To prepare an enabling copy without printing/changing other private settings:

```bash
cd ~/RootedOps
: "${CASH_PRIVATE_DIR:?Set the reviewed private config directory}"
python3 scripts/commerce_cash_config.py --wordpress-env .env --cash-enabled 1 \
  --output "$CASH_PRIVATE_DIR/wordpress.env.cash"
```

Success: a new mode-600 file; no live change. Stop for duplicate flag lines, nonprivate input or an existing output. Inspect locally. At the approved store window, with checkout restricted and the current .env backed up:

```bash
(
  set -eu
  cd ~/RootedOps
  : "${CASH_PRIVATE_DIR:?Set the reviewed private config directory}"
  cp -p .env "$CASH_PRIVATE_DIR/wordpress.env.before"
  install -m 600 "$CASH_PRIVATE_DIR/wordpress.env.cash" .env
  sudo docker compose --env-file .env -f docker/docker-compose.dank-wordpress.yml \
    -p dank-store-test up -d --no-deps dank-wordpress
)
```

This recreates **only** the existing WordPress service to read its environment; coordinate it with the storefront work. No database/ERP/global restart. Verify WordPress and customer hooks immediately using the existing My Account checks. Stop if the service/hostname/volumes differ or health fails. Pause uses the same preparation with `--cash-enabled 0`, preserving other settings and the same service scope. Built-in Woo COD must separately be enabled/restricted to the owner's approved shipping methods in Payments; do not silently enable cash for every delivery method. Existing Clover checkout remains available.
