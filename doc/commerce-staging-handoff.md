# Commerce staging handoff — maintained during offline development

Status: offline implementation in progress. The previous development Linode is
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

Final tested feature SHAs, PRs and CI run links are recorded below as work lands.
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
# Check out the exact reviewed RootedOps SHA from the final checkpoint table.
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

Implementation, tested SHAs, exact inbox/Appsmith commands, CI links and unresolved
defects are being added here. Anything not marked executed remains an open gate.

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
`eafc0c7068e8e99ae9ec405371f9203ba68d73db` (PR #28) has passed local naming/assets/
release checks, two safety tests and discovery of two Playwright journeys. It has
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
real runs before calling #27 proven. Only then implement the MushroomProcess browser
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
