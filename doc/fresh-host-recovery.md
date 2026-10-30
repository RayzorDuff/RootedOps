# Full-stack clean-Linode rehearsal — issue #22

This is the full-stack procedure. The deliberately smaller commerce procedure in
`test-environment-restore.md` is unchanged. Run from a fresh Ubuntu 24.04 Linode
and a clean checkout in your own sudo-enabled user's home directory. No `/opt`
path or particular username is assumed. Do not run this against production.

## Prepare a new host

```bash
cd ~
git clone https://github.com/RayzorDuff/RootedOps.git
cd RootedOps
sudo bash linode_bootstrap.sh
sudo python3 scripts/host_recovery.py validate "$PWD/.test-deployment"
```

Bootstrap prompts for a hostname suffix before installing packages. Accept the default prompt for `-test`, or answer `n` to enter `-test2` for a second rehearsal or leave the next prompt blank for an **empty suffix** (unsuffixed hostnames). Unsuffixed names do not disable test isolation, and this procedure is **not** a production deployment procedure. The chosen suffix is saved in the private deployment receipt and used for generated service URLs, live DNS validation, NGINX vhosts and TLS certificates. Create matching Cloudflare records before the DNS/publish phase.\n\nBootstrap installs Docker/Compose, NGINX/Certbot, rclone, OpenSSL and Python/YAML.
It generates `.test-deployment/.env` and a root `.env` symlink, with private
permissions and distinct local secrets. Existing runtime `.env` or deployment
directories cause refusal; credentials are never replaced. The caller regains
ownership after sudo. The generated Compose files resolve paths from this exact
checkout. Minecraft is explicitly excluded. All other core services, both
WordPress projects, Tymeslot and pinned upstream Rallly are included.

All Docker ports bind to loopback. Networks are internal, so restored services
cannot send production email, payments, OAuth callbacks or webhooks. A local
Mailpit SMTP sink is included; it is not a delivery account. A temporary
self-signed **test-only** Documenso signing certificate is generated. It must
never be used for production documents. Core/HRMS/ESS build arguments remain
operator-selectable; ERP initialization installs the commerce application too.

`validate` checks Compose interpolation (without printing secrets), boolean env
formats, duplicate/occupied ports and missing bind files. `start` builds first,
waits for ERP MariaDB health, initializes its app volume/config/site in order,
then starts the independent projects. This is a large workload; the existing
4 GiB commerce host is not evidence that the whole stack fits or builds reliably.
Use a disposable host with capacity for concurrent databases, Appsmith and builds.

For **fresh empty deployment acceptance A**:

```bash
sudo python3 scripts/host_recovery.py start "$PWD/.test-deployment"
sudo python3 scripts/host_recovery.py status "$PWD/.test-deployment"
```

Do not run `start` first if you intend to restore data: restore refuses existing
containers/volumes. Generated `receipt.json`, `README.txt` and
`startup-receipt.json` identify source revisions, project states and remaining
operator checks. After restart/reboot, rerun `status` and compare the inventory.
A successful CLI exit is not application acceptance: verify authenticated setup,
HTTP responses, database contents and reboot behavior for every service.

## Full backup restore acceptance B

Download the **complete** timestamp directory using the Unix account with the
configured rclone remote, before running privileged recovery. Example:

```bash
install -d -m 700 "$HOME/restore-input"
# Substitute the selected real timestamp. Do not merge snapshots.
rclone copy signaturegate-gdrive-free:SignatureGateBackups/rootedops/SELECTED_TIMESTAMP "$HOME/restore-input"
cd "$HOME/restore-input"
sha256sum --check SHA256SUMS
cd "$HOME/RootedOps"
```

Keep `db/`, `volumes/`, `bind_mounts/`, `meta/.env` and `SHA256SUMS` together.
Do not source a backup `.env` into a shell. Recovery parses it literally and
copies only required encryption keys, not production API/SMTP/OAuth credentials.
The original Frappe site encryption key, n8n encryption key, Appsmith encryption
material, Rallly storage keys and Tymeslot data encryption key must survive.

Before restoring, review `meta/frappe-app-versions.txt`, Docker image metadata
and the archived Compose files. Build/load **matching** application images;
do not silently migrate old data using floating newer Frappe/ERPNext/HRMS/ESS
or MongoDB images. Adjust the private test `.env` build refs/tags and review the
rendered files. The restored Frappe apps volume is retained. Record the review:

```bash
# Build only after selecting matching source/image versions in the private .env.
sudo docker compose --env-file .test-deployment/.env -f .test-deployment/core.yml build
printf '%s\n' 'Reviewed matching source backup and image/app versions' > .test-deployment/IMAGE_COMPATIBILITY_REVIEWED
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" "$HOME/restore-input" --source-site erp.danks.store
```

Replace `--source-site` with the actual site directory in `erpnext_sites.tgz`.
Restoration requires a fresh project, checksum verification, safe/nonempty archive
validation and the explicit compatibility review. Unknown volume/database archives
fail instead of being silently skipped. A `RESTORE_STARTED` marker prevents
silent retry after failure; inspect partial state and use a fresh environment.

The restorer maps original archive names into isolated destination projects.
PostgreSQL logical dumps stop on errors. MariaDB restores only the application
DB, retaining fresh system users; production MariaDB system accounts are never
imported. ERP gets the test hostname and maintenance/scheduler pause. Rallly's
raw cluster retains its PostgreSQL major and original encryption/storage keys.
Appsmith/n8n/NocoDB, WordPress, scheduling and any backed-up LibreChat volumes are
mapped. Bind archives are retained privately; production NGINX is **not**
installed. Documenso signing material and Listmonk uploads are remapped to their
restored private paths. Historical Grav/Minecraft data is retained, not started.

Applications remain stopped after recovery. `restore-receipt.json` lists recovered
archives. This is deliberate: **do not run the fresh-install `start` command after
restoring production data**, because it starts workers and scheduling.

Before launching restored apps, inspect/repoint Appsmith/NocoDB datasource URLs,
disable all n8n workflows with its version-matched CLI, disable ERP outbound email,
webhooks and scheduled jobs, and rewrite each WordPress `home`/`siteurl` plus
serialized internal URLs using its matching WP-CLI. Review embedded production
widgets/callbacks. Restore routes only to the local test databases. Keep all
networks internal throughout the rehearsal. Start only the reviewed services with
the generated Compose files; leave ERP workers/scheduler stopped until verified.
Record SQL/table counts, app record counts, authenticated UI checks, a second
backup/restore round-trip and a host reboot under #22.

The currently supplied migration archives cover MushroomProcess, Appsmith, n8n
and NocoDB only. They cannot demonstrate full ERP/WordPress/scheduling/LibreChat
recovery; those need the complete selected production snapshot. Existing backup
scripts may not have archived LibreChat volumes. If absent, record that as a
missing backup dependency rather than accepting an empty/fresh app as restored.

## DNS and HTTPS

The supplied exports contain all 13 required **-test** A records, each DNS-only
and pointing to **45.33.13.190**. No AAAA records were present. A new Linode needs
these A records repointed to **its own IP** before publishing/certificates:

- danks.store: `erp-test`, `appsmith-test`, `n8n-test`, `nocodb-test`,
  `documenso-test`, `listmonk-test`, `ai-test`, `kids-ai-test`, `qr-test`, `shop-test`.
- rootedpsyche.org: `www-test`, `schedule-test`, `poll-test`.

The scheduling and Rooted Psyche vhosts now match those exported names.
No `grav-test`, `rootedpsyche-test.danks.store`, `schedule-test.danks.store`
or `poll-test.danks.store` record is needed by this full-stack procedure.

```bash
python3 scripts/host_recovery.py dns --deployment "$PWD/.test-deployment" --expected-ip NEW_LINODE_IP --live
# Claim initial accounts via SSH tunnels first; do not expose setup wizards.
sudo python3 scripts/host_recovery.py publish "$PWD/.test-deployment" \
  --expected-ip NEW_LINODE_IP --email YOUR_ACME_EMAIL --accounts-configured
```

Publishing refuses existing installed vhosts, verifies live A/AAAA records against
the new IP, checks NGINX, installs HTTPS and runs renewal dry-run. No DNS changes
are made by the scripts. Keep DNS-only during this direct-origin test.

## External accounts and keys

Missing external keys do not grant production access or enable outbound jobs:

| Integration | Operator action after local service validation |
| --- | --- |
| n8n, Appsmith, NocoDB, WordPress | Claim/restore administrator accounts over SSH tunnels; create test API tokens in the application's account settings; repoint datasources to test service names. |
| ERPNext | Administrator password is in the private generated `.env`; configure companies and dedicated integration user/API credentials only after restore review. |
| LibreChat | Enable registration locally only while claiming the first account, then disable it. Obtain an OpenRouter server API key from its account console if cloud inference is desired; no inference works without it. GitHub MCP needs a separately scoped read-only token. |
| SMTP | Fresh tests use a local sink. Real delivery needs provider SMTP credentials; Gmail uses a separately labeled app password. Never copy production SMTP into the rehearsal. |
| Tymeslot/Rallly OAuth | Create test Google OAuth clients and register the exact test callback URLs from `doc/SCHEDULING.md`; do not reuse production authorization grants. |
| Documenso | Claim admin through the version's documented admin setup, review test certificate and email routing. Signing links/delivery and legal signatures require separate acceptance. |
| Clover/Ecwid | Merchant/store API credentials come from their account consoles. Keep them absent here. Clover remains the immediate live gateway; no Moov implementation or merchant changes. |
| rclone | Configure the intended user's remote with `rclone config`; sudo may use a different configuration. Securely download the selected snapshot, then verify checksums locally. |

## Acceptance record

Automated checks validate generation, isolation, secret formats, source recovery,
Compose configuration and native PostgreSQL/MariaDB smoke checks. They do not
prove a complete restored production stack. Issue #22 owns the manual clean-host
acceptance and is the shared restore gate for #11/#17/#20. Keep it open until
service/data checks, outbound isolation, reboot and round-trip results are recorded.

## Commerce-only restore scope

When using a complete verified snapshot for the ecommerce rehearsal, keep the
already prepared `.test-deployment` and pass explicit `--components` to
`scripts/full_restore.py`. Supported selections are `mushroomprocess`, `erpnext`,
`appsmith`, `n8n` and `dank-wordpress`; the default without this flag remains full
recovery. `--check-only` runs all prerequisites without creating volumes or markers.
See `commerce-staging-handoff.md` for the current owner-selected scope/commands.

Partial restoration does not satisfy this document's full-stack #22 acceptance.
Selected ERP recovery excludes production Redis data and logs. Unselected volumes,
binds, databases and secrets remain untouched. Wait for backup transfer completion,
verify the full manifest and app/image compatibility, and leave restored apps stopped
until production callbacks/credentials/workflows are disabled and targets rebound.

Selected restores do not parse a production env file. Use a private `--key-file`
containing exactly the chosen Appsmith/n8n encryption keys if those volumes are
selected. MP/ERP need no separate source env. Explicit
`--allow-removed-secret-metadata` permits only operator-removed meta/.env and the
Rallly env archive to be absent; all other original hashes and selected payloads
remain mandatory and the original manifest is preserved. Full recovery retains
its complete-snapshot requirements. See the handoff for examples and scope limits.
