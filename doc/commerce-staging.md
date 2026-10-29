# Isolated commerce bring-up

RootedOps #20; related catalog #2, sales #3, MushroomProcess #80/#85/#86.
Only use the disposable Linode 45.33.13.190. Production is 45.33.107.185 and
must not be targeted. DNS names: erp-test, appsmith-test, n8n-test, shop-test
under danks.store. All four resolve to the test Linode as of this validation.

See [repeatable fresh-host restore](test-environment-restore.md) for the current operator path.

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
Rooted Psyche services. The user authorized the attached exports and backup on this test host. Never copy
production `.env` wholesale into staging; retain only encryption keys needed to
recover the selected application data.

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

After the exact baseline fix, 031 and remaining schema migrations through 051
applied successfully on the test Linode. PostgreSQL tests 026, 027, 031 and 051
passed, including synthetic WooCommerce mapping and quantity checks. ERPNext
image build is a separate validation layer; PostgreSQL success does not imply
Frappe application installation or checkout success.

The fresh ERP image build exposed another existing bring-up assumption:
`chown frappe:frappe` fails because the current upstream image has a frappe user
without a same-name group. The Dockerfile now assigns ownership to the existing
user without requiring a nonexistent group. Both local apps receive that fix.

For PostgreSQL backup/restore verification, run
`scripts/commerce_pg_roundtrip.sh /opt/commerce-test`. It refuses another project
or source DB name, dumps the schema/data and restores to a newly created
`mushroomprocess_restorecheck` DB. It never overwrites or drops an existing DB.
The original source remains untouched. Repeating the command intentionally
fails if the restore target already exists; review/remove only that disposable
target separately before repeating.

The first staging image resolved the repository's floating v16 inputs to Frappe
16.54.0 and ERPNext 16.53.0. The existing production versions reported by the owner
are older (16.14.0 / 16.13.0); do not treat staging validation as proof of exact
production-version compatibility or upgrade production implicitly. Pin and test
that deployment separately before production installation.

PostgreSQL dump/restore verification succeeded to a separate
`mushroomprocess_restorecheck` database. No production data was imported.

## Backup restore findings from supplied application archives

The supplied Appsmith and n8n tarballs contained only a root directory. They
cannot restore application state. The old backup script used unprefixed volume
names; Docker can create empty volumes for names that do not exist, while Compose
uses project-prefixed volumes. Backup/restore now resolve actual named volumes
from each container's mount destination and refuse missing sources. Restore
preflights every archive before any volume mutation, rejects empty application
archives and unsafe paths/links, and uses ON_ERROR_STOP for PostgreSQL. Empty
Redis cache/queue state is an explicitly allowed disposable exception.

Application-volume archives must be regenerated from the actual mounted sources;
no application-data restore is claimed for the empty supplied tarballs. Do not
run the full restore script against production as a validation shortcut.

The supplied Ecwid semicolon CSVs reconcile privately using the new CSV adapter.
The supplied PostgreSQL dump also restores fully in the supplemental PGlite
PostgreSQL 18 harness: every COPY table matches source row counts, remaining
schema/constraints load, and migration 051 produces inventory candidates that
join exactly to exported product SKUs. These results do not substitute for a
native PostgreSQL 16 staging restore or live WooCommerce API synchronization.

## Latest native and live verification — 2026-10-29

The user approved test-host Certbot installation. Valid certificates now cover
shop-test, erp-test, appsmith-test and n8n-test.danks.store; NGINX installation
and a simulated renewal succeeded. Earlier failed console paste copies were not
restored. The accepted transfer used authenticated AES-GCM ciphertext over HTTPS,
with an exact checksum, one-use endpoint and a private console key prompt.

The supplied dump restored on native PostgreSQL 16.15 into a separate test DB:
all 92 COPY table counts match, migration 051 applies and 24 inventory candidates
match the exported catalog. ERP staging imported 132 products and 50 immutable
source archives, without stock, Item Price or financial-document changes.
The database's false unhealthy state was the old running container's missing
`mysqladmin` executable; replacing that probe with the official `healthcheck.sh`
restored healthy status without replacing database volumes.

A live WooCommerce REST rehearsal verified 24 draft products, 24 idempotent
retries, refusal of an unowned SKU and reapplication of the MP stock quantity after
a storefront-side change. This used private real ERP/MP snapshots and an explicit
in-memory approval/identity fixture; canonical ERP content remains Draft and no
persistent production mapping is claimed. Remote images and checkout were not
tested. The stricter follow-up verifier compares description text and source/ERP/SEO
metadata, rather than accepting any nonempty description.

Replacement Appsmith/n8n archives are nonempty. n8n SQLite plus WAL passed integrity
checking: 84 workflows, including 20 active in the source. Test copies disable all
workflows and run without external networking. Complete application restore and
cleanup outcomes are tracked in #20; they are distinct from the operator's full
clean-host acceptance under #22. Never infer full restoration from an archive
listing or a container's running state alone. No source credentials or private
catalog/customer/order exports belong in GitHub.
