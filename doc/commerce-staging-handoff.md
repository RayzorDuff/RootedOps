# Commerce staging handoff — maintained during offline development

Status: offline implementation ready for owner PR review; staging acceptance remains open. The previous development Linode is
deleted. Do not contact its IP, reuse its credentials, or infer recoverable state.
This document is the execution record for a **new explicitly authorized** staging
host. It is not permission to deploy, change DNS/merchant settings, process live
payments, cancel Ecwid or retire MushroomProcess production.

## Source baseline and evidence

| Repository | Audited main SHA | Working branch | Baseline |
|---|---|---|---|
| RootedOps | eb39dc7ef862ecd118642768436ef7662e1afb97 | feature/commerce-inbox | #24 recovery; #27 commerce 0.2.0 |
| MushroomProcess | 03b9903181cb0910770dfcbc6cd25a6c165a648d | feature/commerce-fulfillment | #106 ledger; #107 production reconciliation |
| SignatureGate | 21e655b05914ec0978dd08b3b3edea559aa5ece9 | feature/appsmith-e2e-foundation | VERSION 1.1.0; v1.2.0 unreleased |

Tested feature SHAs, PRs and CI run links are recorded in the final checkpoint below.
A commit cannot contain its own SHA; the tested code checkpoint preceding the
final documentation-only commit is the reproducible reference. Fetch exact SHAs
and compare the documentation-only delta before using a subsequent PR head.

Baseline evidence (historical CI, not new deployment acceptance): RootedOps
[40957061294](https://github.com/RayzorDuff/RootedOps/actions/runs/40957061294),
MushroomProcess [41073807981](https://github.com/RayzorDuff/MushroomProcess/actions/runs/41073807981).
Deleted-Linode results in commerce-staging.md are historical only.

## Authority and inactive-by-default boundaries

ERPNext owns commercial Items/prices/content, Customers and accounting documents.
MushroomProcess owns operational availability, reservations, physical movement and
lineage. Woo/Clover events cannot independently move Products/Lots. Historical
imports never submit invoices/payments or replay fulfillment. Clover is the
immediate gateway; Moov is out of scope. No new integration is activated here.
MushroomProcess main preserves production-equivalent behavior through #107;
production remains unchanged until separately approved retirement after cutover.

## New host installation and restore (#22)

After a new Linode is independently authorized and provisioned:

```sh
cd ~
git clone https://github.com/RayzorDuff/RootedOps.git
cd RootedOps
git fetch origin
# Tested code checkpoint; inspect any subsequent documentation/upstream-only merge delta.
git checkout --detach 82ea41698310083085a0d2d491fcef218ebb142a
sudo bash linode_bootstrap.sh
sudo python3 scripts/host_recovery.py validate "$PWD/.test-deployment"
```

Use a nonempty test suffix (default `-test`). Never select unsuffixed production
names for this rehearsal. Exact build refs/tags must match the selected backup;
`.env.example` still has floating Frappe/HRMS/ESS/n8n/NocoDB defaults. Record actual
image digests and `bench version` in the new evidence, not the deleted host's
versions. Current explicit defaults: Appsmith v2.4.2, PostgreSQL 16 for MP,
MariaDB 11.4, Redis 7.2-alpine; Dank WP 7.1.4-php8.3-apache and Woo 11.2.1.
These defaults are not proof of compatibility with any restored backup.

**Restore path:** do not run fresh-install `host_recovery.py start` first.
Download one complete timestamp from the operator's configured rclone remote into
a private directory. Keep db/, volumes/, bind_mounts/, meta/.env and SHA256SUMS
together. Never source the archived .env. Example (replace the remote/timestamp):

```sh
install -d -m 700 "$HOME/restore-input"
rclone copy REVIEWED_REMOTE:REVIEWED_BACKUP_PATH/TIMESTAMP "$HOME/restore-input"
(cd "$HOME/restore-input" && sha256sum --check SHA256SUMS)
# Select matching image/source refs in the PRIVATE .test-deployment/.env first.
sudo docker compose --env-file .test-deployment/.env -f .test-deployment/core.yml build
printf '%s\n' 'Reviewed matching backup/image/app versions' > .test-deployment/IMAGE_COMPATIBILITY_REVIEWED
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" "$HOME/restore-input" --source-site erp.danks.store
```

Use the actual archived Frappe site name. Restore requires fresh containers/volumes
and leaves apps stopped; RESTORE_STARTED forbids silent partial retry. Inspect the
restore receipt and private quarantine. Use a new environment after partial failure,
not a destructive reset of an uncertain target. Full commands/limitations remain
in fresh-host-recovery.md. The uploaded commerce subset cannot prove full recovery.

**Fresh empty path only:** `sudo python3 scripts/host_recovery.py start "$PWD/.test-deployment"`.
Do not use that command to start restored production jobs.

## Secrets, domains and outbound isolation

Keep generated private keys/passwords distinct from production. Retain only the
original encryption material needed to decrypt restored Frappe/n8n/Appsmith data;
all operational tokens, merchant keys, SMTP, OAuth and external callbacks stay
blank/replaced with test credentials. Never commit credentials or private exports.

Required commerce domains: erp-test, appsmith-test, n8n-test, shop-test and optionally
nocodb-test.danks.store. Full #22 also uses documenso-test, listmonk-test, ai-test,
kids-ai-test, qr-test.danks.store and www-test/schedule-test/poll-test.rootedpsyche.org.
Verify A/AAAA against the **new host's IP** before publishing; current DNS is unknown.
No DNS edits are authorized by this handoff. Use SSH loopback tunnels first.

Generated Docker networks are internal and published ports are loopback-only.
Keep ERP workers/scheduler stopped, maintenance/pause enabled; disable outbound
Email Accounts, Notifications, Webhooks and scheduled integrations. Deactivate
**all** restored n8n workflows with the version-matched CLI before running n8n.
Rebind every Appsmith/NocoDB datasource to local test services. Disable WP cron,
transactional email, gateway/webhook callbacks and payment plugins; use a local
SMTP sink. Audit embedded REST URLs and encrypted credentials. Internal networks
remain mandatory even when application-level toggles are set. Enable only selected
reviewed test flows; never attach unrestricted egress just to make a test pass.

## Database and Frappe readiness

Do not replay the full MP baseline against a restored database. Inventory applied
migrations and function signatures first; apply reviewed missing **forward** SQL
only. Retain full filenames for both 051 migrations. Commerce requires
051_erp_commerce_catalog.sql and 052_commerce_order_ledger.sql; #107 adds
053_preserve_product_spawn_timezone.sql. New session migrations are recorded in
its final checkpoint. Stop ingress/workers while changing schema.

Frappe needs frappe/erpnext v16 and rootedops_commerce (plus restored HRMS,
employee_self_service and rootedops_payroll at matching versions). On the reviewed
backend container, run `bench --site erp-test.danks.store list-apps`, install missing
rootedops_commerce with `bench --site erp-test.danks.store install-app rootedops_commerce`,
then `bench --site erp-test.danks.store migrate`. Keep maintenance/scheduler pause.
Record each app SHA/version and image digest; do not silently upgrade restored apps.

## Ordered acceptance work

1. Run `make commerce-test` in RootedOps and the MP commerce PostgreSQL CI commands
   against a disposable synthetic DB. Keep restore acceptance under #22 separate.
2. Compile synthetic fixtures using `integrations/commerce/migrate_reviewed.py`
   catalog/history (see commerce-offline-development.md). Real source requires
   reviewed currency, categories, attributes, Item tax templates/accounts, media,
   customer identity and discount/shipping/tax allocations. CSV lacks full variants.
3. Archive raster blobs/checksums, upload to reviewed ERP/WP test origins and verify
   receipts. Install the ERP-owned SEO plugin; check rendered HTML with/without
   Yoast, cache invalidation and canonical URLs. Compare every product/variation,
   SKU, price/currency, tax class, category and image ID against the reviewed plan.
4. Enable commerce_catalog_import_enabled only for the reviewed batch. Call
   rootedops_commerce.api.import_reviewed_catalog as Sales Manager, then disable.
   Replay and verify Item/Price/content/mapping counts and no stock changes.
5. Enable commerce_history_import_enabled only for reviewed history. Call
   rootedops_commerce.history.import_history, replay and compare durable IDs/totals.
   Confirm audit-only drafts, no invoice/payment/delivery/stock entries or mail.
6. Exercise the new inbox/worker commands documented below, with synthetic signed
   raw Woo payloads. Test duplicate, lost-response retry, stale/same-revision conflict,
   failure/dead-letter/replay, pending/payment/cancel and partial/full refund cases.
7. Check MP gross vs reservation-adjusted quantities across provider aliases.
   Physical movement must be explicitly acknowledged through an operational
   transaction; a Woo completed flag or refund must not mutate physical lineage.
8. SignatureGate E2E commands below remain **post-v1.2.0**, opt-in and outside that
   release gate. A real Appsmith app/isolated DB must be used; static checks and
   Playwright --list are not browser acceptance. MP expansion waits for that proof.

## Clover and ERP financial acceptance

Use the official Clover Payments for WooCommerce extension, pinned and reviewed
on the new WP/Woo/PHP versions. Obtain sandbox-only merchant/public/private keys
privately; do not copy live keys. Merchant provider must separately confirm online
entitlement, account/credential continuity, fees and settlement after Ecwid exit.
Test authorize-only vs capture, failed/abandoned checkout, void, partial/full refund,
webhook retries/order, transaction ID uniqueness, captured gross/refunded total,
currency, fees/settlement/chargebacks and ERP document links. A paid flag is not
capture evidence. Controlled live checkout/cutover needs separate explicit approval.

## New work checkpoint (updated throughout implementation)

The final checkpoint below records executed offline/CI evidence. Anything not
marked executed remains an open gate.

## Rollback, cleanup and no-go checklist

Disable new ingress/workers/site flags and payment plugins before reverting code.
Preserve source identities, event/error history and outstanding reservations for
reconciliation; never drop live holds or delete audit documents to force a retry.
Delete only explicitly owned disposable test DBs/volumes after evidence capture.
Remove downloaded working backup copies after rehearsal, preserving original
production backups and retention policies. Reboot and backup/restore round-trip
must be recorded for the new host before recovery acceptance.

Ecwid retirement is NO-GO until: complete catalog/media/customer/history parity;
all publishers/ingress account for reservations and legacy allocations; end-to-end
ERP/MP identity and physical fulfillment correctness; real Appsmith role/DB effect
checks; Clover sandbox plus separately approved live checkout/settlement; merchant
entitlement confirmed; #22 recovery/reboot/round-trip accepted; redirect/QR parity;
reversible DNS/cutover plan and verified rollback backups; explicit owner approval.
No production-branch retirement, subscription change or live payment is authorized.

### Current new integration commands and configuration

RootedOps 0.3.0 adds opt-in `commerce_order_integration_enabled`. New source DocTypes
Commerce Order State and Commerce Financial Link require `bench migrate` before use.
MP requires migration 054_commerce_operational_bridge.sql after 051/052/053. Review
the entire change before applying it to a restored database; do not rerun baseline.

Install the staging worker's only external Python dependency in a private virtualenv:

```sh
python3 -m venv .commerce-venv
.commerce-venv/bin/pip install 'psycopg[binary]==3.3.6'
export COMMERCE_STAGING_ONLY=1
# Set COMMERCE_INBOX_DSN and MP_TEST_DSN privately; never paste credentials into Git.
# Accepted database names: commerce_test, commerce_integration_test, mushroomprocess_test.
# Accepted hosts: localhost, 127.0.0.1, commerce-postgres. No hostaddr override.
.commerce-venv/bin/python integrations/commerce/runtime.py init
.commerce-venv/bin/python integrations/commerce/runtime.py status
.commerce-venv/bin/python integrations/commerce/runtime.py serve --config /PRIVATE/inbox-config.json
# Separate terminal; processes at most one leased event:
.commerce-venv/bin/python integrations/commerce/runtime.py work-once --config /PRIVATE/inbox-config.json
# Replay only a dead letter, retaining successful target receipts:
.commerce-venv/bin/python integrations/commerce/runtime.py replay --event-key woocommerce TEST_SITE EVENT_SHA256
```

The private config has `sites[TEST_SITE]` containing `secret_envs` (current/previous
secret environment-variable names), exact Woo product/variation→SKU/ERP Item/MP
mapping, and reviewed gateway→clover mapping. It also has `approved_erp_drafts`,
keyed `woocommerce|TEST_SITE|WOO_ORDER_ID`, containing explicitly reviewed Customer,
Company, currency, Items/qty/rates, actual tax/shipping accounts, dates and docstatus=0.
No automatic discount/customer/account inference is allowed. Set ERP_AUTHORIZATION
privately for a test Sales Manager token. The HTTP server binds 127.0.0.1:8100 only,
path `/webhooks/woocommerce/TEST_SITE`; never expose it as production ingress.

Sign the exact raw fixture bytes with base64 HMAC-SHA256 using the configured
secret, POST application/json with X-WC-Webhook-Signature to that loopback route.
HTTP 202 acknowledges durable receipt, not fulfillment/accounting. Invalid requests
return 400; storage failure returns retryable 503 without exposing error details.
Run identical/redelivered fixtures, inspect status counts and source/target IDs.
The worker stores MP and ERP receipts separately. Lost remote responses must retry
against idempotent target identities, not duplicate accounting or inventory.
Five failed attempts dead-letter with a safe error code; inspect private evidence
before explicit replay. No automatic reservation expiry or release on worker error.

Enable the ERP order site flag only during tests. The worker calls
`rootedops_commerce.order_service.stage_order`; only reviewed drafts are created.
Accounts Manager may explicitly call `attach_financial_documents` to link existing
submitted ERP invoice/receipt documents with matching party/company/currency and
exact order/allocation. It creates/submits no financial document. Partial invoices,
net-fee and foreign-currency receipts require separate reconciliation, not guessing.
A unique Commerce Financial Link prevents the same invoice/payment being claimed
by another source order. Re-run delivery with verified links to project them to MP.
Merchant evidence still comes only from an independently verified Clover adapter.

Operational test transaction (operator role, parameterized driver calls): match
verified capture using mp_commerce_match_payment; link verified ERP IDs using
mp_commerce_link_erp; call mp_commerce_confirm_reservation. Move explicit synthetic
Products to Shipped using the existing operational function, then call
mp_commerce_acknowledge_products(provider,site,order,movement_reference,lines_json)
**in that same transaction**. Each line contains line_id and product_ids. Test one
of two units first, retry identical reference, refresh Woo snapshot, then cancel:
only unshipped holds release. Refund must not move a shipped Product back. New
string-only mp_commerce_commit_fulfillment calls now refuse unverified release.
Lot/bulk allocation, non-unit packages and returns/reversals remain manual gates.

### SignatureGate post-release harness checkpoint

SignatureGate feature/appsmith-e2e-foundation checkpoint
`5cdd875ae4d78f5531c28c4b76ef8c197e475eb3` (PR #28) has passed local naming/assets/
release checks, three safety tests and discovery of two Playwright journeys. It has
**not** passed actual Appsmith login/navigation/cash browser execution. Its v1.2.0
scope/version/export are unchanged. RootedOps companion CI runs only its pinned
native DB/guard contracts, never a substitute browser UI or a SignatureGate release gate.

On the authorized new staging host, use SignatureGate/e2e/README.md verbatim:
`npm ci --prefix e2e --ignore-scripts`; configure private E2E_DB_PASSWORD,
E2E_INSTANCE_TOKEN and E2E_DATABASE_URL for the dedicated signaturegate_e2e DB/user;
`docker compose -f e2e/compose.yml up -d`; opt in E2E_ALLOW_RESET=1; run
`npm run --prefix e2e db:reset`, `db:check`, then `node e2e/database.test.mjs`.
That reset refuses signaturegate/signaturegate_test, unknown hosts/roles, an
unmarked nonempty DB or wrong instance marker before destructive operations.
Do not rebind any actual app to the disposable fixture DB.

Import a separate real SignatureGate E2E Appsmith clone and rebind every datasource
to postgres-e2e. Create purpose-built artificial reviewer/practitioner accounts;
never reuse live passwords or OAuth. Review actual accessible role/name/label
selectors into ignored e2e/selectors.private.json. Set E2E_APPSMITH_URL to the
explicit local/test origin, E2E_APP_PATH to /app/signaturegate-e2e/ACTUAL_ROUTE,
E2E_SELECTORS_FILE, E2E_SELECTORS_REVIEWED=1, E2E_POST_RELEASE_ACK=post-v1.2.0 and
private E2E_REVIEWER_PASSWORD. From e2e: `npx playwright install chromium`, `npm test`,
then inspect the private HTML report and retained failure traces/screenshots.
No reports or auth state may be published without privacy review. Repeat reset and
real runs before calling #27 proven. Only then implement the MushroomProcess #109 browser
follow-up with its own DB, app clone, fixtures and authority/permission checks.

### Catalog parity and signed-fixture command details

The `sync.py` staging apply path now requires `commercial` review on every mapping:
item_group, currency, price_list, woocommerce_category_ids, ERP Item Tax Template
(or reviewed_no_item_tax=true), Woo tax status/class and canonical ERP File URL→Woo
media ID map. It selects exactly one active Item Price using the ERP server's
as_of_date, checks UOM/currency, emits prices/categories/tax/uploaded media IDs and
checks the actual Woo store currency before writes. Missing/overlapping prices,
expired rates, tax/group drift and missing media IDs refuse publication. Template
prices remain excluded. Example commands (all named files must be reviewed anew):

```sh
python3 integrations/commerce/migrate_reviewed.py catalog SOURCE_PLAN.json REVIEW.json --media-manifest UPLOADED_MEDIA.json --output PRIVATE_CATALOG.json
python3 integrations/commerce/migrate_reviewed.py history SOURCE_EXPORT.json HISTORY_REVIEW.json --output PRIVATE_HISTORY.json
python3 integrations/commerce/sync.py PRIVATE_MP_SNAPSHOT.json PRIVATE_REVIEWED_MAP.json --output PRIVATE_WOO_PLAN.json
# Only after reviewing the dry-run and test credentials/targets:
python3 integrations/commerce/sync.py PRIVATE_MP_SNAPSHOT.json PRIVATE_REVIEWED_MAP.json --output PRIVATE_WOO_RESULT.json --apply-staging
# Run the loopback receiver first, then sign a wholly synthetic Woo fixture:
python3 integrations/commerce/send_fixture.py SYNTHETIC_WOO_ORDER.json --site TEST_SITE
# Repeat exactly, then process delivery and inspect aggregate state:
python3 integrations/commerce/send_fixture.py SYNTHETIC_WOO_ORDER.json --site TEST_SITE
python3 integrations/commerce/runtime.py work-once --config /PRIVATE/inbox-config.json
python3 integrations/commerce/runtime.py status
```

Use raw fixture fields shown by test_inbox_postgres.py: stable Woo id,
date_modified_gmt, status, currency/total, reviewed payment_method and transaction_id,
line_items with stable id/product_id/variation_id/SKU/integer quantity, and complete
refunds. Change status only with a later date_modified_gmt, re-sign the exact bytes,
and test cancel/failed/refunded snapshots. A partial refund is a negative Woo
refund total; full-refund status requires refund sum equal to order total. Never
substitute real customer/payment data. The inbox retains verified raw bodies
privately for source audit; status output exposes only aggregate safe error codes.

Historical imported Sales Orders are now blocked from submission by a server hook;
Invoices referencing those orders are blocked too. Operational cancelled/failed/
refunded source orders require review before ERP submission. The order service
still creates drafts only; no merchant event posts accounting. Native tests must
verify those protections after installing the new hooks.

After Accounts Manager explicitly links submitted documents, refresh MP identities
without redelivering a Woo snapshot:

```sh
python3 integrations/commerce/runtime.py reconcile-order --config /PRIVATE/inbox-config.json --order-key woocommerce TEST_SITE WOO_ORDER_ID
```

This refuses until the latest durable event has completed delivery, reads current
ERP source references, and idempotently links them to MP. It neither ingests an
order again nor confirms payment/reservations. Submitted operational Sales Orders
can resolve stable references and receive source-status updates; cancel/refund of
a submitted order returns reconciliation_required and never cancels ERP documents.
Accounting reversals/credit notes remain explicit Accounts Manager work.

## Final offline code checkpoint and evidence (2026-10-30)

| Repository / PR | Branch | Tested code SHA | New evidence |
|---|---|---|---|
| [RootedOps #28](https://github.com/RayzorDuff/RootedOps/pull/28) | feature/commerce-inbox | 82ea41698310083085a0d2d491fcef218ebb142a | [integration 41087056935](https://github.com/RayzorDuff/RootedOps/actions/runs/41087056935), [foundation 41087056842](https://github.com/RayzorDuff/RootedOps/actions/runs/41087056842), [recovery 41087057028](https://github.com/RayzorDuff/RootedOps/actions/runs/41087057028): all green |
| [MushroomProcess #108](https://github.com/RayzorDuff/MushroomProcess/pull/108) | feature/commerce-fulfillment | 3d948a66ecc6ff9850e67bea92ce5b2c1952f605 | [native rebuild/concurrency + production contracts 41084995240](https://github.com/RayzorDuff/MushroomProcess/actions/runs/41084995240), [lint 41084995225](https://github.com/RayzorDuff/MushroomProcess/actions/runs/41084995225): green |
| [SignatureGate #28](https://github.com/RayzorDuff/SignatureGate/pull/28) | feature/appsmith-e2e-foundation | 5cdd875ae4d78f5531c28c4b76ef8c197e475eb3 | Pinned native PG/guard contracts and Playwright discovery green in RootedOps integration run above; local make validate/release-check pass; **browser execution not performed** |

RootedOps code checkpoint includes main through 904a233a661cde6c0abc2877dee46460d1d21630;
main continued with unrelated payroll/NACHA fixes during this session. Final PR
sync includes main 1cdfd03e51488539cbe7aa3df0788fb8651a15b9, preserving those upstream files. MP/SG audited main SHAs remain those in the
baseline table. MP production was read-only, observed at
c6f27240e693d4d8d04ee259ac51ba522d1a5f91; no update/delete was made. SG VERSION,
release gate and application exports and MP existing application exports are unchanged.
All new tree objects were checked against local complete Git tree hashes.

New tests executed: Root local 56 tests (55 pass, PHP CLI absent locally);
foundation CI includes the PHP SEO hook test; native Frappe **7 tests pass**;
native inbox **3 tests pass**, covering concurrent receipt, commit/lost-response
retry, fencing/dead-letter/replay and financial-reference refresh without ingestion;
SG **3 guards pass**, native canonical role denial/access, cash+audit/reset/marker
checks pass, **2 browser tests discovered only**. MP CI covers native forward SQL,
legacy inventory/view/production contracts and concurrent oversell protection.
CI is synthetic and disposable; it contains no production customer/payment data.

Native image `frappe/erpnext:v16.13.0` resolved to
`sha256:d956e13cde1e3c09c52cffcbfd0476afdcf13fc9b8902cfd7205da650054e8dc`;
`bench version` reported ERPNext 16.13.0, Frappe 16.14.0 and rootedops_commerce 0.3.0.
That is the tested combination, **not** proof that floating Docker build arguments
or production backup apps match it. CI uses PostgreSQL 16, MariaDB 11.4 and Redis
7.2-alpine. SignatureGate harness 0.1.0 pins Playwright 1.64.1 and pg 8.23.1;
Appsmith v2.4.2 is a proposed local fixture image, not a browser-tested version.
Record actual digests for every staging image after bootstrap/restore.

### Source checkout and precise migration/import commands

```sh
# Separate sibling clones, never check out or mutate MP production.
git clone https://github.com/RayzorDuff/MushroomProcess.git ../MushroomProcess
git -C ../MushroomProcess checkout --detach 3d948a66ecc6ff9850e67bea92ce5b2c1952f605
git clone https://github.com/RayzorDuff/SignatureGate.git ../SignatureGate
git -C ../SignatureGate checkout --detach 5cdd875ae4d78f5531c28c4b76ef8c197e475eb3
```

For a restored MP database, inspect existing functions/tables and applied SQL
receipts; **apply only missing reviewed forward files** with `psql -v ON_ERROR_STOP=1`.
The full sequence after 050 is 051_erp_commerce_catalog.sql,
051_extraction_batch_provenance.sql, 052_commerce_order_ledger.sql,
053_preserve_product_spawn_timezone.sql, 054_commerce_operational_bridge.sql.
Do not infer migration state from numeric prefix alone (two 051 files), rerun the
baseline, or substitute production DSNs. Example for **054 only after proving
051/052/053 are installed**, using a private local test DSN:

```sh
# runtime connect_test enforces local host and exact disposable database name.
PYTHONPATH=integrations/commerce .commerce-venv/bin/python - <<'PY'
import os
from pathlib import Path
from runtime import connect_test
with connect_test(os.environ['MP_TEST_DSN'])() as db:
    if db.execute("SELECT to_regclass('public.mp_commerce_shipments')").fetchone()[0]:
        raise SystemExit('054 already present; inspect function versions rather than reapplying')
    db.execute(Path('../MushroomProcess/schema/pgsql/054_commerce_operational_bridge.sql').read_text())
PY
# In the reviewed ERP backend container (generated core.yml service):
sudo docker compose --env-file .test-deployment/.env -f .test-deployment/core.yml exec erpnext-backend bench --site erp-test.danks.store list-apps
sudo docker compose --env-file .test-deployment/.env -f .test-deployment/core.yml exec erpnext-backend bench --site erp-test.danks.store migrate
```

Install missing commerce app first as described above; the image must contain
its exact reviewed source before `install-app`/`migrate`. Never run native fixture
bench run-tests against the restored site; those tests belong on a fresh disposable
CI site. Commerce site flags default disabled. After reviewing configuration:

```sh
sudo docker compose --env-file .test-deployment/.env -f .test-deployment/core.yml exec erpnext-backend bench --site erp-test.danks.store set-config commerce_catalog_import_enabled true
# ERP_AUTHORIZATION is a private test Sales Manager API authorization value.
PYTHONPATH=integrations/commerce .commerce-venv/bin/python - <<'PY'
import json,os
from pathlib import Path
from ecwid_migrate import api,private_write
plan=json.loads(Path('PRIVATE_CATALOG.json').read_text())
result=api('https://erp-test.danks.store/api/method/rootedops_commerce.api.import_reviewed_catalog',
    os.environ['ERP_AUTHORIZATION'],'POST',{'payload':json.dumps(plan)})
private_write(Path('PRIVATE_ERP_IMPORT_RECEIPT.json'),result)
PY
sudo docker compose --env-file .test-deployment/.env -f .test-deployment/core.yml exec erpnext-backend bench --site erp-test.danks.store set-config commerce_catalog_import_enabled false
```

Repeat the exact reviewed import and compare returned identities/counts. Import
history with the same guarded pattern using commerce_history_import_enabled and
rootedops_commerce.history.import_history; disable the flag even after a failure.
Operational worker uses commerce_order_integration_enabled. Inspect flags via
private site config; never print credentials. An ERP operator must review/approve
Commercial Product Content before sync (the importer deliberately creates Draft).

Parity commands are the compiler/sync dry-run above plus read-only Woo REST GETs
for every returned product/variation ID. Compare ERP Item/Price/tax template,
source key/hash, SKU, parent/attributes, visible rich text, prices/currency,
category IDs, tax class, uploaded image IDs and SEO metadata to PRIVATE_WOO_PLAN.
The legacy `scripts/commerce_live_sync_smoke.py ENVIRONMENT` checks simple draft
copy/SEO/stock/retry only, using an in-memory approval fixture and no images; it
**cannot** satisfy full catalog parity, variations, tax/media or checkout acceptance.
Do not reuse its deleted-host private snapshots; regenerate them on the new host.

For precise native lifecycle regression commands use the MP workflow file and
`schema/pgsql/tests/052_commerce_order_ledger.sql`,
`schema/pgsql/tests/054_commerce_operational_bridge.sql` and
`python3 schema/pgsql/tests/052_commerce_concurrency.py` **only in the fresh
synthetic commerce_test CI database**. They include executable synthetic payment,
ERP link, reservation confirmation, physical acknowledgement, partial shipment,
refresh, cancellation and refund cases and roll back fixture SQL. Do not execute
fixture SQL against restored production data. The Root integration workflow runs
`python integrations/commerce/test_inbox_postgres.py -v` on a separate fresh DB.

### Specific remaining review and deployment gates

- No live Clover adapter/plugin checkout, capture evidence, settlement import,
  accounting reversal or net-fee/FX reconciliation is enabled. Financial links
  reference existing submitted documents; automatic invoice/payment generation
  and full native submitted-financial-document scenarios remain acceptance work.
- Product acknowledgements do not replace operational movement authorization.
  Lot/bulk/non-unit allocation, expiry, return intake and stock/accounting reversals
  require reviewed contracts/UI. Dedicated least-privilege worker/operator grants
  must be reviewed before activation; new trusted functions revoke PUBLIC execute.
- Active legacy Ecwid workflows are preserved and still need reservation-aware
  publication/fulfillment conversion. No dual-channel activation until gross stock,
  held demand, shipped units and legacy allocations reconcile without overselling.
- MP #80 catalog/GTIN administration and complete ledger controls in Fulfillment
  are absent. MP #109 is a separate browser extension plan **blocked on SG #27**.
- Review category hierarchy/existing target IDs, jurisdiction/account/tax mapping,
  customer duplicates/country/address normalization, Contact consent/phone quality,
  discounts/shipping allocations and source-image rights/errors manually. API
  export is required where CSV lacks variation/options/customer/history fields.
  Passwords, saved payment instruments, unsupported custom fields and login/consent
  history are not inferred or replayed. Preserve originals in private archives.
- Fresh #22 full restore and reboot/round-trip, ERP/MP/Woo live parity, rendered SEO,
  actual Appsmith UI and Clover validation remain new-host tasks. No historical
  deleted-host test has been represented as reproducible current acceptance.

## New-host rehearsal checkpoint — October 30, 2026

The owner has prepared a new Ubuntu test host and handed over its authenticated
non-root console. Bootstrap configuration already exists; do not regenerate it.
Current RootedOps main is d3d5ce29229fe435da14a755368bb06ecc2b89bc (#28 merged),
MP main is 127bae5769492ee6e653be26e33d00347b00e4a0 (#108 merged). The commerce
code delta from the tested Root checkpoint is documentation plus upstream payroll
changes; preserve both. Exact infrastructure identifiers and raw endpoint evidence
stay private on the host.

Executed new-host evidence: generated configuration passes Compose interpolation,
internal-network/loopback-port, unique/free-port and bind-source validation. Docker
has no containers or volumes. All 13 required test domains passed direct A/AAAA
queries against both Cloudflare authoritative nameservers (26 endpoint checks):
expected test IPv4, authoritative answers and no AAAA records. The corrected ERP
and shop records are present. An extraneous DNS record still needs owner review;
no DNS edits or certificates were issued. The private evidence file is
`.test-deployment/dns-authoritative-check.json`. DNS success is not HTTP/TLS or
application acceptance.

**Scope update from owner:** restore only commerce dependencies from the complete
backup being copied. Do not restore unrelated Rooted Psyche WordPress, scheduling,
Listmonk, LibreChat, SignatureGate production DB, Documenso or Minecraft. SignatureGate
browser proof later uses its own artificial fixture DB, not a production DB restore.
This selected rehearsal does not complete #22's full-stack restore acceptance.

### Selected restore into the existing bootstrap configuration

`full_restore.py --components` selects MushroomProcess, ERPNext, Appsmith, n8n and
optionally Dank WordPress. Omit the option only when a full-stack rehearsal is
explicitly intended. No environment re-render is needed. Selected ERP restores
apps/sites only, not logs or production Redis queue/cache data. No production bind
archives, unrelated application secrets or source database passwords are copied
by the selected path. Original Appsmith/n8n encryption keys and the site's ERP
configuration are retained as required to decrypt restored data. Database users
are local to isolated projects. Review WordPress DB config against its generated
test credentials before starting a restored WP volume.

Wait for the operator's explicit **copy complete** notice before any backup scan,
checksum, version review or restore; an incomplete snapshot must never be accepted.
Discover the actual backup directory without assuming that a displayed `~` path
is root's or the deployment account's home. Then:

```sh
# Use the verified complete snapshot, kept private; never source meta/.env.
# Review its app/image version metadata before building or marking compatibility.
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" /PRIVATE/COMPLETE_BACKUP \
  --source-site ACTUAL_SOURCE_SITE --components mushroomprocess erpnext appsmith n8n --key-file /PRIVATE/restore.keys --check-only
# Only after all preflight checks and compatibility review succeed:
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" /PRIVATE/COMPLETE_BACKUP \
  --source-site ACTUAL_SOURCE_SITE --components mushroomprocess erpnext appsmith n8n --key-file /PRIVATE/restore.keys
```

Both commands retain full SHA256SUMS validation, fresh-host/project/volume checks,
archive safety and explicit image compatibility requirements. The first command
creates no containers, volumes, database records or restore markers. Missing
selected archives or original encryption keys refuse before mutation. The restore
receipt records selected components and explicitly distinguishes the limited scope.
Applications remain stopped for callback/datasource/account review. Do not invoke
fresh-install `start` afterward.

If the complete backup includes the independent Dank WooCommerce DB/HTML archives,
add `dank-wordpress` to the selection before the first restore. Otherwise keep it
out and provision a fresh isolated Dank store only after restore prerequisites are
satisfied; do not import the Rooted Psyche store into it. Start only explicit reviewed
service names, keeping ERP workers/scheduler and n8n workflows disabled. Certificate
and public-access work still waits for initial account/access-control completion.

Pending: backup copy/checksums and image compatibility review, selected native
restore and data comparisons, application isolation/remapping, live catalog/order
integration, real Appsmith browser proof and Clover sandbox acceptance. None has
been marked passed merely because bootstrap or DNS validation succeeded.

### Completed-backup compatibility review

The operator confirmed transfer completion. The full checksum manifest passed on
the new host. Selected DB/volume archives are present; there is no independent
Dank WordPress backup, so its staging store must be initialized fresh rather than
restoring Rooted Psyche WordPress. Archived versions: ERPNext 16.13.0, Frappe 16.14.0,
HRMS 16.4.7, Employee Self Service 2.2.2, rootedops_payroll 0.4.10. Commerce is not
installed in that source snapshot and needs the reviewed 0.3.0 app copied/installed
only after safe restore and datasource/job isolation.

For the custom image use ERPNEXT_IMAGE_TAG=v16.13.0,
ERPNEXT_HRMS_BRANCH=be4178aa04054ceece66d2c9ea157552962bd663 and
ERPNEXT_ESS_BRANCH=e13041752c1a218d6954ce9d7a2145031e762fa6. The HRMS tag and ESS
commit were resolved from their official repositories. `fetch-frappe-app.sh` lets
these existing build variables select immutable commits as well as branches/tags;
its local Git test verifies exact checkout and refusal to overwrite a directory.
Keep restored app source and image dependencies compatible; do not upgrade HRMS/ESS
or invoke payroll processing just to install commerce.

Appsmith and n8n image availability is being checked against archived registry
digests before any restore marker/volume is created. Do not substitute current
`latest` for an unavailable archived n8n image. Record pull/build digests and
`bench version` after native verification before marking compatibility reviewed.

### Secret-minimal selected recovery

Selected recovery never opens or parses the source production `meta/.env`. MP and
ERP recovery require no separate source env file. Appsmith/n8n require an explicit
`--key-file` owned/protected by the operator (mode 0600 or stricter), containing
exactly the selected original encryption keys: APPSMITH_ENCRYPTION_PASSWORD,
APPSMITH_ENCRYPTION_SALT and/or N8N_ENCRYPTION_KEY. Extra production credentials
in that file are rejected. Keep values out of chat, Git and logs. Alternatively,
leave those encrypted volumes out and initialize fresh test instances from reviewed
repository app/workflow exports. Do not silently switch encrypted data to new keys.

When the operator has deliberately removed secret metadata from a complete backup,
`--allow-removed-secret-metadata` acknowledges only absent `meta/.env` and
`bind_mounts/rallly-selfhosted-env.tgz` during a selected restore. Every other
manifest entry must still exist and match its original SHA256. Every selected
payload must be represented in the manifest. Unsafe/duplicate paths and payload
hash drift refuse; the source manifest is never rewritten. The receipt lists the
omitted secret metadata explicitly. This is a documented limited recovery, not an
assertion that the original full snapshot remains unmodified.

Example with no source env or separate encryption secrets needed:

```sh
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" /PRIVATE/COMPLETE_BACKUP \
  --source-site ACTUAL_SOURCE_SITE --components mushroomprocess erpnext \
  --allow-removed-secret-metadata --check-only
```

The same invocation without `--check-only` performs that selected restore only
after compatibility and all remaining checks pass. Full-stack recovery without
component selection retains the original strict complete-manifest/source-key rules.

### Native image verification on the new staging host

The pinned custom ERP image built successfully. Network-isolated disposable image
probes report all six expected package versions: Frappe 16.14.0, ERPNext 16.13.0,
HRMS 16.4.7, ESS 2.2.2, rootedops_payroll 0.4.10 and rootedops_commerce 0.3.0.
Image ID: sha256:650bf324f27b820d9e110bea6e4af90f8246b1cdadb734027ef4613646b75af6
(local custom image ID, not a public registry manifest). Reproduce after the pinned
build with `docker run --rm --network none --entrypoint bench
rootedops-erpnext:v16.13.0 version`; use the image's
`/home/frappe/frappe-bench/env/bin/python` and importlib.metadata.version for the
six-package probe because the base image's apps.txt lists only frappe/erpnext.

Archived Appsmith/n8n digests pulled successfully. Private generated configuration
also pins database/cache images to the archived registry digests. The compatibility
receipt is based on those pulls, package probes and matching backup metadata; it
is not database/application acceptance. No production env was parsed. Original
hashes for all remaining backup files verified with exactly the two documented
secret-metadata omissions. MP/ERP selected restore preflight is now being exercised;
Appsmith/n8n credential restoration remains deferred without keys-only input.

### First native restore preparation failure

Selected restore check-only passed on the new host. The first actual attempt then
failed immediately with `unknown flag: --no-deps`: this Compose version does not
support that flag on `create`. No containers/volumes or database data were created;
the failure marker/log remain preserved pending inspection. Do not call that
attempt a restored database or erase an uncertain partial restore.

The corrected volume preparation uses `up --no-start --no-deps SERVICE`; it creates
the selected stopped container without starting dependencies or application code.
The tar helper runs with `--network none`. Both the full/selected and legacy commerce
paths now use this supported command. Native CI `scripts/restore_volume_ci.py`
restores exact synthetic file bytes through both implementations, asserts the
application remains in `created` state and its dependency is not created, and
cleans only its guarded fresh fixture projects. Do not run that CI fixture on the
staging/restored database host.

A retry on the existing prepared environment is appropriate only after explicit
inspection proves that this attempt performed no data/container/volume mutations.
Archive the original failure marker/log as attempt evidence, keep the generated
credentials/configuration, revalidate the empty destination and then rerun with
the corrected tested revision. A genuine partially restored data set still requires
the documented separate recovery decision rather than this no-op preparation case.

### Selected restore result on the new staging host (2026-10-30)

The empty-destination inspection was completed and its evidence archived before
retrying. Selected recovery at `b08bb675f38a4fe9818251449a7902d2c3e45d79`
completed with exit 0: ERP sites/apps volumes and the ERP database were restored,
and all 92 PostgreSQL COPY-table counts matched the MushroomProcess dump.
Only the two database containers run; the ERP application container remains
created/stopped. No workers, scheduler, Appsmith, n8n, WordPress or unrelated
applications were started. This is selected recovery evidence, not full-stack
#22 acceptance or integrated commerce acceptance.

Private `restore-receipt.json` records the four selected payloads, the two deliberate
secret-metadata omissions and `apps_started=false`. ERP site maintenance and
scheduler-pause flags and the `erp-test` hostname were verified. Restored Email
Accounts (incoming/outgoing), Webhooks and Notifications were disabled directly
in the isolated database before any application startup. Exact commercial record
counts were saved privately in `restored-database-health.json`; do not publish
customer records, source database identities or credentials as test artifacts.

`mariadb-check --check` returned 0 (938 output lines). Nine sequence tables report
the expected engine-does-not-support-check note; all other statuses were OK.
This database integrity check does not replace Frappe migrations or accounting
reconciliation. The restored MP information-schema inventory contains 135 public
relations, including views, with 92 physical tables.

Two rehearsal corrections are now covered by regression tests:

- Full bootstrap generates `MP_BRIDGE_DB_NAME=mushroomprocess_test` and
  `MP_BRIDGE_DB_USER=mushroomprocess_test`, matching commerce runtime test guards.
  The still-empty destination was updated to these names before database import;
  generated passwords were preserved. Existing populated databases must not be
  renamed merely by editing environment variables.
- Noninteractive Compose subprocesses close stdin unless explicit SQL input or a
  stream was supplied. The native restore initially suspended on background
  terminal input; it was resumed with `fg` and completed, without a second import
  or marker reset. Both restore paths now retain SQL stdin and suppress credential
  arguments in exceptions. Run restore in the foreground or redirect stdin from
  `/dev/null`; never restart a suspended or partially completed restore blindly.

Recovery regression tests: 15 passed locally. `make commerce-test`: 56 tests,
55 passed and one PHP-dependent test skipped because local PHP is unavailable;
CI must execute that adapter test. PR #29 native stopped-volume regression passed
for both recovery implementations in [Actions run 41142467924](https://github.com/RayzorDuff/RootedOps/actions/runs/41142467924).
The follow-up branch starts from main `9b0d64ddf0619278caed3fe43e8f351e0989e643`
and retains PR #30's environment-derived target hostname, including `-test2` support.

### Forward migrations and ERP initializer repair

After auditing the restored schema, applied only these missing forward files:
`051_erp_commerce_catalog.sql`, `052_commerce_order_ledger.sql`,
`053_preserve_product_spawn_timezone.sql`, `054_commerce_operational_bridge.sql`.
All commands exited 0; row counts in all 92 existing MP tables remained unchanged.
The new ledger has zero orders and the spawn wrapper has
`TimeZone=America/Denver`. Private `mp-migration-receipt.json` records source SHA,
file hashes and preservation evidence. Do not replay the baseline or the unrelated
051 extraction migration merely because its numeric prefix matches.

The restored Frappe site lists the five source apps at their expected versions.
The first commerce installation failed with `ModuleNotFoundError` because two
Compose initializers had multiline **string** commands with `bash -lc` entrypoints.
Compose resolved these to 8 and 7 arguments respectively: Bash executed only
`set`, returned 0, and never copied commerce or configured Redis. An exit code
alone was insufficient evidence of initialization.

Both initializer commands now use a one-element script list. Generated staging
configuration was repaired in place with its prior copy preserved privately;
no environment regeneration, database import or credential replacement occurred.
Resolved argv now contains exactly one script, the actual initializers exited 0,
and the commerce package files appeared in the restored apps volume. Use the
bench virtualenv Python for import probes, not the image's system Python.
Existing generated deployments need the same reviewed command-shape repair or
they will retain the old strings. `host_recovery.py validate` now rejects split
`bash -lc` commands; fresh rendering inherits the corrected template. Regression
coverage checks script shape, commerce inclusion and Bash syntax (16 recovery tests).

Reproduce initialization after reviewing private generated configuration:

```sh
cfg="$PWD/.test-deployment"
sudo docker compose --env-file "$cfg/.env" -f "$cfg/core.yml" run --rm --no-deps erpnext-apps-init
sudo docker compose --env-file "$cfg/.env" -f "$cfg/core.yml" up -d --no-deps erpnext-redis-cache erpnext-redis-queue
sudo docker compose --env-file "$cfg/.env" -f "$cfg/core.yml" run --rm --no-deps erpnext-configurator
```

These commands prepare files/cache only. Commerce install/migrate, catalog/order
acceptance, TLS, browser E2E and payment acceptance must still be recorded from
their actual results; none follows from the initializer's success alone.

### ERP health and closed TLS acceptance (2026-10-31)

The post-install native Frappe probe passed: all six apps are installed, eight
commerce DocTypes exist, and Item, Item Price, Customer, Sales Order, Sales Invoice,
Payment Entry, Contact and Address counts match the private pre-migration baseline.
Email, Webhook and Notification enable flags remain zero; maintenance and scheduler
pause remain enabled. Run Python probes with the bench virtualenv interpreter and
`os.chdir('/home/frappe/frappe-bench/sites')` before `frappe.init(site=...)`.
The earlier missing `/home/frappe/logs/database.log` exception was a probe working
directory error, not evidence of failed database recovery. Private evidence:
`erp-migration-acceptance.json`. No tests or synthetic accounting postings were run
against historical ERP records.

Both Cloudflare authorities and public resolvers were rechecked for the four
commerce test domains. A webroot ACME certificate covers erp-test, appsmith-test,
n8n-test and shop-test.danks.store; verified HTTPS requests to all four return 403.
Certbot renewal dry-run passed. NGINX configuration validation and a renewal deploy
hook (`nginx -t` followed by reload) passed. No application proxy/setup interface
was published. Private evidence: `tls-acceptance.json`. This does not authorize
removing the access gate or attaching unrestricted Docker egress.

The fresh Dank shop has no corresponding archive in this snapshot; use a fresh
synthetic installation, never the Rooted Psyche WordPress backup. The new
`scripts/commerce_wordpress_offline.py` consumes the existing private `dank.yml`,
requires a fresh dedicated project and verified WooCommerce ZIP, and mounts a
staging-only isolation plugin. It refuses production hostnames, public ports,
external networks/volumes and archive drift before starting containers. Cron,
automatic updates, external HTTP, email delivery and all checkout gateways stay
disabled. WordPress 7.1.4 and WooCommerce 11.2.1 match the reviewed official
[WordPress release](https://wordpress.org/news/2026/10/wordpress-7-1-4/) and
[WooCommerce release](https://developer.woocommerce.com/2026/10/09/woocommerce-11-2-1-release-notes/).

Download the official plugin ZIP on the host, record/review its SHA256, then use:

```sh
sudo python3 scripts/commerce_wordpress_offline.py "$PWD/.test-deployment" \
  /PRIVATE/woocommerce.11.2.1.zip --sha256 REVIEWED_ARCHIVE_SHA256
```

Pull the reviewed images before running; internal app networks cannot download
packages. The installer adds a private Compose override at
`private/wordpress-offline.yml`. Include this override in every later shop/CLI
command. Credentials and acceptance receipts stay private. Existing containers,
volumes or installation credentials cause refusal; on failure the application
stops and evidence remains for inspection rather than silent reinstallation.
No Clover credentials, merchant enrollment or real payments are involved.

Offline checks at this checkpoint: 16 recovery tests passed; commerce suite ran
60 tests (59 passed, one local PHP skip). Native shop acceptance and image digests
must be recorded after actual execution. Appsmith browser proof, reviewed catalog
parity, integrated order/fulfillment/refund tests and Clover sandbox acceptance
remain outstanding. Restoration/TLS success alone is not cutover approval.

### Native fresh-shop installation and ingress limitation

At `cfdf6a8129e81b50274f7fd4131b57cf4ef20fa5`, the offline installer completed
successfully on the isolated staging host. WordPress 7.1.4 and WooCommerce 11.2.1
initialized from the official ZIP with SHA256
`5317434cb381b5fdc7c1dd6ee258324f08c390976aaf8d1199f2a0e9a3ab8586`.
The private receipt verifies disabled cron, blocked HTTP/email and zero enabled
payment gateways. Only the dedicated Dank database/HTML volumes were created;
Rooted Psyche was not restored or started. `shop-input-receipt.json` records pulled
image IDs/digests; `private/wordpress-offline-receipt.json` records installation.
CI passed at this revision: [commerce](https://github.com/RayzorDuff/RootedOps/actions/runs/41214204153),
[recovery](https://github.com/RayzorDuff/RootedOps/actions/runs/41214204152),
and [native integration](https://github.com/RayzorDuff/RootedOps/actions/runs/41214204140).

Docker accepted the loopback publication but the running internal-only WordPress
container reports `80/tcp: null`; the first authenticated HTTPS API request returned
502 because no loopback listener existed. Do not fix this by attaching restored
applications to an unrestricted network. Docker documents host access to bridge
container addresses; its maintainers also explain the internal-only publication
behavior in [moby discussion 53256](https://github.com/moby/moby/discussions/53256).
For this Linux rehearsal, host NGINX now uses the inspected private WordPress
address after verifying its Compose project and sole internal network. No
container egress was added. **Refresh this upstream after WordPress container
recreation**, before testing requests; the address is not a stable deployment ID.
Private `shop-upstream-receipt.json` records container identity and refresh need.
Durable automatic upstream refresh remains a deployment acceptance dependency.

Only the shop hostname's `/wp-json/wc/v3/` route is proxied, and requests lacking
Authorization return 401. WordPress validates supplied application passwords;
an Authorization header alone does not grant access. Root/admin/setup paths
remain 403, as does the same API path under the ERP hostname. Credentials are
held only in the private test credential file. These access checks passed before
catalog writes. This is an API-only rehearsal, not browser/checkout acceptance.

After authenticated API readiness, exercise synthetic draft catalog behavior:

```sh
sudo python3 scripts/commerce_woo_native_smoke.py "$PWD/.test-deployment"
```

The fixture tests simple/variable product upserts, separate SKU/variation identities,
prices/categories/reviewed no-tax behavior, SEO metadata, stock drift correction
and ownership refusal. It never changes ERP/MP data, publishes products, transfers
media or executes checkout. Its receipt must be recorded after actual execution;
this command is not evidence of restored-catalog parity or financial reconciliation.

### Native catalog, media and SEO results

Synthetic catalog proof passed at `def0dbbd2ca5dc74bfbbd1e758fb30ad3585eb6a`;
native media/SEO proof passed at `8e7bb7d2a11851fb94ba00ce407b5ba9d6fd309b`.
Both scripts passed again against the same shop, retaining the same product,
variation and image IDs. Verified draft-only simple/variable upserts, separate
variation SKUs, price/category/no-tax fixture projection, SEO metadata, stock
drift correction and unowned-target refusal. A deterministic 24x24 PNG was uploaded
through the authenticated WordPress media API and linked by image ID in WooCommerce.
The installed SEO adapter returned expected values through core/Yoast-compatible
hooks and emitted the escaped native description tag. **Yoast itself is absent;
no browser-rendered product page or live checkout was tested.** ERP media transfer,
actual restored catalog parity and real tax policy remain acceptance gates.

Reproduce after checking protected ingress and the private installation receipts:

```sh
sudo python3 scripts/commerce_staging_ingress.py "$PWD/.test-deployment" --apply
sudo python3 scripts/commerce_woo_native_smoke.py "$PWD/.test-deployment"
sudo python3 scripts/commerce_woo_media_smoke.py "$PWD/.test-deployment"
```

The ingress helper checks the exact running app/project, reviewed image ID and sole
internal network, refreshes the host upstream and validates/reloads NGINX. It
restores the prior configuration on validation/reload failure. It adds no Docker
egress and leaves root/admin/setup pages closed; only authenticated shop Woo API
and exact media-upload routes are forwarded. Run it after every WordPress
container recreation. Fresh offline installs include both staging isolation and
SEO must-use plugins. No restoration or credential regeneration is needed.

Native pulled image references:

| Component | Image manifest digest |
| --- | --- |
| WordPress 7.1.4 / PHP 8.3 Apache | `wordpress@sha256:12ec50e21cb81a5ea964669d434578b7da4a101a45aef83f5f1c2227bcd1b058` |
| WordPress CLI / PHP 8.3 | `wordpress@sha256:6bcc7bb91f5157c4b915e74ee131873e99c1c1ff48f602e4a6f6cd17827305cb` |
| Dedicated shop MariaDB 11.4 | `mariadb@sha256:d1891ede5a559f1086f55053bb8cc1569b0298338c4d72d71725a7f74f6ba620` |

Private receipts: `private/woo-native-smoke.json`, `private/woo-native-media.json`,
`private/woo-native-media-seo.json`. Do not publish credentials or private source
exports as CI artifacts. Original Ecwid product/order CSVs were located and passed
private identity/SKU preflight; the plan is explicitly review-only with an
unconfirmed store namespace. Currency, authoritative store/customer/line identities,
variant completeness, full galleries, tax mappings and export completeness still
need review/enrichment. No source catalog, customer or historical financial records
were applied. The synthetic native proof does not satisfy those source-data gates.

### SignatureGate preparation and Clover review checkpoint

SignatureGate main `40e752f8d73057bf670edb8785772814d74d1998` passed local
validate/release checks, three harness guard tests and discovery of its two browser
journeys. A separate fresh `signaturegate-e2e` project was prepared on staging:
PostgreSQL 16, Appsmith CE 2.4.2 and pinned Playwright 1.64.1 runner. Its private
`signaturegate-e2e/images.json` records actual pulled digests. Runner dependencies
installed, and `database.mjs reset`, `database.mjs check` and `database.test.mjs`
all exited 0 against only the dedicated synthetic `signaturegate_e2e` database.
Restored operational databases and production accounts were not reset or reused.

**No authenticated Appsmith browser journey has passed.** First setup inspection
was inconclusive and console administration needs renewal before diagnosis can
finish. Use a bounded browser probe with unconditional browser close, an outer
process timeout and a named disposable runner that can be stopped independently.
Do not reboot or stop restored database services to recover a browser probe.
Next: inspect actual setup/labels, create purpose-built test accounts, import the
reviewed clone, rebind all datasources/actions, isolate external services, then run
the real login/navigation/cash journeys twice with backend/audit assertions and
private traces/screenshots. SignatureGate #27 remains post-v1.2.0; MushroomProcess
#109 stays blocked on that reliable proof. Containers/seed success is not UI proof.

RootedOps [PR #42](https://github.com/RayzorDuff/RootedOps/pull/42) contains the
independent read-only Clover sandbox evidence adapter and gateway compatibility
review (`doc/clover-sandbox-evidence.md` after merge). It preserves durable inbox
payloads and requires a reviewed numeric-ID/display-number crosswalk. No Clover
API request, plugin activation, merchant settings change or payment was executed.
Merchant credentials, actual response shape, HPOS/checkout, refunds/settlements and
post-Ecwid entitlements remain acceptance gates. Native commerce/recovery CI passed
for PR #41 at `b35fb89cf86418df35dfe7ba429736d6ff5e6839` and sandbox-contract
CI passed for PR #42 at `436bfbfa1b37d53947e6b4cb7a699ce338d1cce0`:

- [Staging native integration](https://github.com/RayzorDuff/RootedOps/actions/runs/41216607630)
- [Staging recovery](https://github.com/RayzorDuff/RootedOps/actions/runs/41216607624)
- [Sandbox native integration](https://github.com/RayzorDuff/RootedOps/actions/runs/41217923159)
- [Sandbox recovery](https://github.com/RayzorDuff/RootedOps/actions/runs/41217922960)

These results remain separate from final staging order-lifecycle and cutover
acceptance. Ecwid stays active; production deployment, live payment, subscription
changes and MushroomProcess production-branch retirement remain unauthorized.
