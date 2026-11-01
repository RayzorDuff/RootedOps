# Shared test2 readiness continuation

This checkpoint applies only to the shared test2 deployment. The older `-test`
host is retired; none of its private credentials or runtime evidence is reused.
No full restore, Appsmith reimport, production action or application Git branch
change is part of this continuation. RootedOps #22 remains open.

## Source and database preparation

Host RootedOps source: main `401fd5dbb021af00fe7964ed5d90cf4e4700d01e`.
SignatureGate schema: main `e4ac0b51566c241b3df83881192a22e4d5e0e2a9`, independently
cloned at `/home/rootedops/SignatureGate-test2-schema`.

Created the previously absent `signaturegate_test` database from template0 on
`rootedops-full-test-signaturegate-postgres-1`, then applied `db/schema.sql` and
`db/seeds/organization_terminology.sql`. The source schema contains transaction
boundaries; this was an absent-target bootstrap, not an atomic in-place upgrade.
The first absence guard refused because formatted psql output was compared to a
scalar; corrected `-At` guard confirmed zero targets before CREATE. No failed
attempt imported data. Do not replay this bootstrap now that the DB exists.

No production test records were copied. Native synthetic suite: **42/47 passed**.
Five failures are tracked in SignatureGate #30: directory reviewer/practitioner
fixture authority, two missing agreement-type fixtures and removed legacy identity
columns. Do not weaken authorization to make old fixtures pass. Two read-only
checks without an explicit rollback were wrapped in transactions.

Created `signaturegate_test_app` with LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE,
NOINHERIT, NOREPLICATION and NOBYPASSRLS. Grants cover test public-schema DML and
sequence usage only; no owner-only trigger privileges were added. Catalog checks
found **zero accessible public relations and zero executable security-definer
functions in the restored SignatureGate DB**. This does not claim CONNECT is
revoked there: PostgreSQL PUBLIC connection defaults remain unchanged.

Password-authenticated application-role cash end-to-end and paper-storage checks
passed. Atomic Intake and base paper upload owner-suite runs hit missing trigger
privileges during deliberate fault injection; do not count those role runs as
passed or grant DDL just for fixtures. Owner-suite versions passed. Appsmith
authenticated binding and browser journeys remain unverified.

Private evidence (root-readable; never publish credentials):

```text
.test-deployment/test2-readiness/signaturegate-schema/receipt.json
.test-deployment/test2-readiness/signaturegate-schema/sql-tests.json
.test-deployment/test2-readiness/signaturegate-schema/role-readiness.json
.test-deployment/test2-readiness/signaturegate-schema/authenticated-role-tests.json
.test-deployment/test2-readiness/signaturegate-schema/connection.private.json
```

The connection file has the new synthetic-only credential. Use a secure operator
workflow to bind only the dedicated test datasource to `signaturegate-postgres`,
5432, `signaturegate_test`, user `signaturegate_test_app`. Do not paste its password
into chat or Git, substitute the restored database, or reset an existing target.

## ERP dependency repair

The old running image had Frappe metadata 16.54.0 with restored source 16.14.0,
and failed importing posthog. Built a separate image with:

```sh
cd /home/rootedops/RootedOps
sudo docker build -f docker/erpnext-custom.Dockerfile \
  --build-arg ERPNEXT_IMAGE_TAG=v16.13.0 \
  --build-arg ERPNEXT_HRMS_BRANCH=be4178aa04054ceece66d2c9ea157552962bd663 \
  --build-arg ERPNEXT_ESS_BRANCH=e13041752c1a218d6954ce9d7a2145031e762fa6 \
  -t rootedops-erpnext:test2-restored-v16.13.0 .
```

Actual local image ID:
`sha256:908a38651afd93e0e2823cfee7ce4c07db02293c072f6c006d2ea26c311d3438`.
This is a local image ID, not a registry manifest digest. Restored versions:
Frappe16.14.0, ERPNext16.13.0, HRMS16.4.7, ESS2.2.2, payroll0.4.10;
built commerce0.3.0. Original source volumes and existing image tag were retained.

Private `private/erp-restored-image.yml` changes ERP image selection and normalizes
the two initializer scripts to one Bash argument. It does not replace core.yml or
regenerate .env. Always include it for ERP operations:

```sh
cfg="$PWD/.test-deployment"
sudo docker compose --env-file "$cfg/.env" -f "$cfg/core.yml" \
  -f "$cfg/private/erp-restored-image.yml" -p rootedops-full-test ps
sudo docker exec rootedops-full-test-erpnext-backend-1 \
  bench --site erp-test2.danks.store list-apps
```

Executed apps-init/configurator and backend-only startup; no queue workers or
scheduler started. Initial native Frappe DB/count probe passed. Before commerce
migration, disabled one restored outbound Email Account and six Notifications;
incoming email/Webhooks were already off. Commerce install-app and migrate both
exited0. Private `erp-native-pre-commerce.json` and `erp-native-acceptance.json`
confirm unchanged counts for Item, Item Price, Customer, Sales Order, Sales
Invoice, Payment Entry, Contact and Address. All six apps and eight commerce
DocTypes are present. Outgoing email/Notifications remain disabled; maintenance
and pause_scheduler remain1. A live read-only n8n database check still shows
84 workflows/zero active. This proves counts/health, not financial reconciliation.
No customer/history imports, accounting postings or physical movements were run.

## Remaining routing and storefront gates

The prior redacted inventory remains applicable: saved N8N, mushroomprocess-n8n
and NocoDB-public datasource origins reference production. No actions were run
through them. Rebind only through reviewed application configuration, preserving
paths/auth and legitimate browser callbacks; do not change source master or
chatgpt_development branches without their own review. Appsmith-to-local PG/n8n
TCP checks and Appsmith/n8n health HTTP200 were verified previously on this host.

The offline WordPress installer now accepts only receipt-matched `-test` or
`-test2` ERP names and derives the correct shop URL. Production/empty suffix and
receipt/environment mismatch still refuse before Docker mutations. Existing
Dank projects or credentials still refuse reinstallation. This does **not** yet
adapt the HTTPS catalog/media/ingress tools, which remain `-test`-specific.
Do not run those tools against test2 or fake their TLS/image receipts.

### Native fresh-shop result

The dedicated Dank project was verified empty (no containers, volumes or previous
credentials) before running installer code `ba81b56a90fe68af94f825abeaa0b3a0bda67c12`
from `/home/rootedops/RootedOps-commerce-test2`, against the existing generated
configuration. The official Woo11.2.1 ZIP matched SHA256
`5317434cb381b5fdc7c1dd6ee258324f08c390976aaf8d1199f2a0e9a3ab8586`.

A restrictive operator umask exposed two permission edges: the source ZIP was
0600 and the mounted MU-plugin directory was700. The installer stopped the web
container on failure. Inspection confirmed WordPress was already installed;
no reset or installer replay occurred. Retained the original admin credential,
staged a verified container-readable ZIP copy under the private parent, repaired
only the plugin directory traversal mode, and resumed plugin installation/options.
The source ZIP remains0600 and private deployment parents remain700. Code now
handles both edges and retains a private operation error log on failure.

Native assertions passed: WordPress7.1.4, WooCommerce11.2.1, home URL
`https://shop-test2.danks.store`, disabled cron, blocked external HTTP/email and
zero available gateways. The web/database containers are running on their sole
internal network. Created a staging application password privately; authenticated
Woo REST currency/products GETs returned200 through the inspected private bridge
address with the correct Host/proxy headers. CurrencyUSD and empty products are
synthetic installation defaults, not reviewed Ecwid mapping evidence. This did
not test public TLS, storefront browser rendering or checkout.

Evidence: `private/wordpress-offline-receipt.json`,
`test2-readiness/woo-internal-rest.json`, `shop-input-receipt.json` (actual image
IDs/digests), private failure/resume logs. The original detached job's failed
state is historical; the verified installation receipt records the completed
resume. Do not rerun the fresh installer against this populated project.

For later non-destructive CLI checks, include the isolation override:

```sh
sudo docker compose --env-file "$cfg/.env" -f "$cfg/dank.yml" \
  -f "$cfg/private/wordpress-offline.yml" run --rm --no-deps \
  dank-wordpress-cli core version
sudo docker compose --env-file "$cfg/.env" -f "$cfg/dank.yml" \
  -f "$cfg/private/wordpress-offline.yml" run --rm --no-deps \
  dank-wordpress-cli plugin get woocommerce --field=version
```

Both Cloudflare authorities returned the approved test2 IPv4 and no AAAA for
ERP/Appsmith/n8n/shop test2 names, with authoritative flags. Private evidence:
`test2-readiness/dns-authoritative.json`. No DNS edits or certificates issued in
this continuation. Native Compose interpolation of PR43's three private URL
variables also passed unset/blank/explicit cases without starting probe containers;
receipt `test2-readiness/compose-url-check.json` supersedes the incomplete attempt.

At `ba81b56`, all three CI workflows passed:
[commerce](https://github.com/RayzorDuff/RootedOps/actions/runs/41257425037),
[recovery](https://github.com/RayzorDuff/RootedOps/actions/runs/41257425110),
[native contracts](https://github.com/RayzorDuff/RootedOps/actions/runs/41257425063).
The archive-permission regression increases local commerce coverage to74 tests
(73 passed, one local PHP skip); latest commit checks must pass before merge.

Public Woo access, catalog parity, webhook/order lifecycle and Clover checkout
on this host remain acceptance gates. Never restore Rooted Psyche WP
into the Dank project. Preserve all internal networks; no public admin/setup
exposure, outbound integrations, merchant changes or payments are authorized.

Rollback: stop only newly enabled app services before reversing image/config
selection; retain restored volumes, app/source tags, audit records and evidence.
Do not drop the new test DB while another workstream is using it. Preserve the
Appsmith rollback archive and all existing restore receipts.
