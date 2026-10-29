# Isolated commerce bring-up

RootedOps #20; related catalog #2, sales #3, MushroomProcess #80/#85/#86.
Only use the disposable Linode 45.33.13.190. Production is 45.33.107.185 and
must not be targeted. DNS names: erp-test, appsmith-test, n8n-test, shop-test
under danks.store. All four resolve to the test Linode as of this validation.

## Baseline

Ubuntu 24.04, Git, Docker Engine/Compose, PostgreSQL client and Python PyYAML
are required. The fresh Linode had Git but no Docker. Ubuntu repository packages
`docker.io docker-compose-v2 postgresql-client python3-yaml` provide these.
Use public HTTPS clones; no repository SSH key is necessary for public reads.
The original LINODE_SETUP.md starts the entire stack; **do not use its unqualified
`compose up -d` here**. The host has 3.8 GiB RAM, ~495 MiB swap and ~72 GiB free disk
before images. Stage services sequentially; Appsmith plus Frappe may exceed RAM.
Do not run heavy builds alongside Appsmith. Do not upgrade Ubuntu for this task.

```bash
cd /opt/RootedOps
python3 scripts/commerce_staging.py /opt/commerce-test
cd /opt/commerce-test
docker compose --env-file .env -f compose.yml config --quiet
docker compose --env-file .env -f compose.yml up -d mushroomprocess-bridge-postgres
```

The renderer selects PostgreSQL/n8n/Appsmith and ERPNext dependencies only.
It creates a separate Compose project, fresh credentials, isolated volumes and
loopback-only ports. No listmonk, scheduling, Minecraft, SignatureGate or
Rooted Psyche services. Do not copy production .env or import customer exports
into this staging host until an explicit data-handling decision.

## PostgreSQL

Use `psql -v ON_ERROR_STOP=1`. Apply pre-load SQL in numeric order excluding
`100_load.sql`; do not import repository CSV exports into the clean test DB.
Seed only synthetic fixtures. The legacy post-load `124_*` module assumes data
and should be validated separately. New `051_erp_commerce_catalog.sql` is
additive and provides `erp_item_code` plus provider-neutral stock reads. Run
`schema/pgsql/tests/051_erp_commerce_catalog.sql` after installation.

## ERPNext

```bash
cd /opt/commerce-test
docker compose --env-file .env -f compose.yml build erpnext-backend
docker compose --env-file .env -f compose.yml up -d erpnext-db erpnext-redis-cache erpnext-redis-queue erpnext-apps-init erpnext-configurator erpnext-backend
docker compose --env-file .env -f compose.yml --profile erpnext-init run --rm erpnext-bootstrap
```

The app has to exist in the built image **and** shared apps volume. Existing
volumes receive the new app directory only when absent; app updates require a
reviewed apps-volume refresh before migrate. Never delete a production apps
volume. No production site is installed with Commerce automatically: bootstrap
requires `ERPNEXT_INSTALL_COMMERCE=1`, enabled by the staging renderer only.

Run Frappe integration tests with `allow_tests` enabled on the disposable site.
Then start frontend, websocket, queue-short/long and scheduler. Check memory
before starting n8n and Appsmith. Use current repository Frappe pins; the base
image's default version-16 tag is floating, so record its digest before accepting
reproducibility. HRMS/ESS branches also need immutable pins for a release build.

## UI and TLS

Ports are bound to loopback. Do not expose a first-run setup wizard publicly.
Finish local owner/admin initialization before routing authenticated test UI
traffic. Nginx test vhosts and ACME TLS should use only the test hostnames.
Import Appsmith JSON into a new app and change every PostgreSQL/n8n datasource
to the new environment. Never reuse exported production datasource credentials.
Import only inactive reviewed n8n workflows; no production schedules or mail.
The new manual snapshot workflow is intentionally read-only and inactive.

## WooCommerce

`docker/docker-compose.dank-wordpress.yml` is opt-in and has separate DB/secrets,
volumes and loopback port 8097. Configure DANK_WP_* in a dedicated env file.
Do not start it until initial ERP/database validation is complete. The WordPress
image matches the existing repository baseline; verify supported WordPress,
WooCommerce and official Clover plugin versions before public checkout. Plugin
activation, credentials, merchant terms, refunds and order lifecycle tests remain
acceptance gates. No plugin is silently installed or merchant settings altered.

Back up MariaDB with a consistent dump plus WordPress media, and test restoration
under a different Compose project before cutover. Keep backup credentials private.

## Validation commands

```bash
make commerce-test
python3 -m unittest discover -s tests -v
```

Local unit tests do not replace `bench run-tests`, real PostgreSQL regression
or checkout tests. Record each layer separately in #20; never describe an
unexecuted staging or payment flow as verified.

## First execution findings

Docker/Compose installed successfully from Ubuntu repositories. Minimal rendered
Compose validates and the PostgreSQL service starts without unrelated services.
The documented numeric SQL replay successfully applies 001 through 030, but 031
rejects the fresh generated `vc_lots` signature. Its production-only fingerprint
guard cannot accept the repository's own clean baseline. Do not bypass it blindly:
the paired MushroomProcess branch allowlists the exact baseline signatures,
retaining rejection of unknown view definitions. Rerun both legacy
navigation and commerce snapshot regressions before continuing.

The broad RootedOps unittest suite also has a pre-existing static assertion in
`test_bookworks_native_release_contract.py` expecting the retired text
`Already published; use reviewed update workflow`. The current main-branch PHP
supports approved published revisions. Commerce tests are independent of this
known unrelated assertion; PHP syntax checking is skipped if PHP is unavailable.
