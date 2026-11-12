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

Bootstrap prompts for a hostname suffix before installing packages. Accept the default prompt for `-test`, or answer `n` to enter `-test2` for a second rehearsal or leave the next prompt blank for an **empty suffix** (unsuffixed hostnames). Unsuffixed names do not disable test isolation, and this procedure is **not** a production deployment procedure. The chosen suffix is saved in the private deployment receipt and used for generated service URLs, live DNS validation, NGINX vhosts and TLS certificates. Create matching Cloudflare records before the DNS/publish phase.

Bootstrap installs Docker/Compose, NGINX/Certbot, rclone, OpenSSL and Python/YAML.
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

### Private first-run access

On the deployment host, use the generated Compose project to locate the
Appsmith container's address on its internal network. Some Docker installs
do not activate the host-side port mapping for an internal network, even if
Compose lists it in the configuration.

```bash
deployment="$PWD/.test-deployment"
core=(sudo docker compose --env-file "$deployment/.env" -f "$deployment/core.yml")
appsmith_container=$("${core[@]}" ps -q appsmith)
sudo docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$appsmith_container"
```

From your workstation, forward a local-only port to the returned container
address using the Linode as the SSH endpoint.

```bash
ssh -N -L 127.0.0.1:18080:APPSMITH_CONTAINER_IP:80 SSH_USER@TEST_LINODE_IP
```

Open `http://127.0.0.1:18080` to claim the Appsmith account. For n8n or NocoDB,
look up the corresponding service address and use container port `5678` or
`8080`. Repeat the lookup after recreating a container. Confirm the
intended upstream responds before running public HTTPS acceptance.

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

A full recovery now requires a **format-2 nightly snapshot** produced by the
repaired `backup/backup-stack.sh`. Its checksummed `meta/recovery-bundle.json`
identifies installed groups, every required payload, actual mounts and immutable
runtime image IDs, platforms and recovery methods. Published images use verified
immutable registry digests; their bytes are omitted. The optional
`images/runtime-images.tar.gz` contains only required local/custom images with
no verified published source, such as locally built ERPNext/Documenso. No separate manual image
export, floating-tag rebuild or `IMAGE_COMPATIBILITY_REVIEWED` marker substitutes
for this bundle. Older snapshots remain available for explicitly scoped subset
recovery; they cannot prove complete full-stack acceptance.

Review the inventory and `meta/frappe-app-versions.txt`, then load and verify the
public digests and necessary custom images and pin the **generated isolated**
Compose files. This step starts
no containers and preserves their internal networks, loopback ports and generated
test credentials. The source ERP backend image also supplies the initializer and
bootstrap services. Source groups explicitly recorded as not installed remain
behind an inactive profile, rather than becoming misleading fresh installations.

```bash
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" "$HOME/restore-input" --prepare-images
sudo python3 scripts/host_recovery.py validate "$PWD/.test-deployment"
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" "$HOME/restore-input" --source-site erp.danks.store --check-only
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" "$HOME/restore-input" --source-site erp.danks.store
```

Image preparation verifies snapshot checksums/completeness, pulls pinned public
images, loads only the archived custom bytes, checks exact local IDs and removes
floating builds from restored runtime
services and sets `pull_policy: never`. Its private receipt binds source inventory
to the generated Compose files. Restore refuses missing service payloads even when
a hand-edited SHA256SUMS would otherwise pass. Source bind mounts (including Board
supplements and LibreChat configuration) are restored into private local quarantine
and remounted there; original external paths are not contacted. The production
Documenso signing certificate/passphrase stay archived and the generated TEST-only
certificate/passphrase remain active in the test configuration.

See [nightly-recovery-bundle.md](nightly-recovery-bundle.md) for the producer-side
repair, maintenance pause, image selection/size report and operator rerun.

Replace `--source-site` with the actual site directory in `erpnext_sites.tgz`.
Restoration requires a fresh project, checksum verification, safe/nonempty archive
validation and an exact-image preparation receipt. Unknown volume/database archives
fail instead of being silently skipped. A `RESTORE_STARTED` marker prevents
silent retry after failure; inspect partial state and use a fresh environment.

The restorer maps original archive names into isolated destination projects.
PostgreSQL logical dumps stop on errors. MariaDB restores only the application
DB, retaining fresh system users; production MariaDB system accounts are never
imported. ERP gets the test hostname and maintenance/scheduler pause. Rallly's
raw cluster retains its PostgreSQL major and original encryption/storage keys.
Appsmith/n8n/NocoDB, WordPress, scheduling and any backed-up LibreChat volumes are
mapped. Bind archives are retained privately; production NGINX is **not**
installed. Production Documenso signing material stays quarantined; Listmonk uploads and
other runtime bind payloads are remapped to restored private paths. Historical Grav/Minecraft data is retained, not started.

Applications remain stopped after recovery. `restore-receipt.json` lists recovered
archives. This is deliberate: **do not run the fresh-install `start` command after
restoring production data**, because it starts workers and scheduling.

Rallly uses the local Mailpit service on port 1025 without SMTP authentication.
Leave both `SMTP_USER` and `SMTP_PWD` absent from the generated Rallly
`.env`. An older generated configuration with only `SMTP_USER` set causes
Rallly to fail environment validation and return HTTP 500. For an existing test
deployment, remove both fields and recreate only the Rallly web container.

Before launching restored apps, inspect/repoint Appsmith/NocoDB datasource URLs,
disable all n8n workflows with its version-matched CLI, disable ERP outbound email,
webhooks and scheduled jobs, and rewrite each WordPress `home`/`siteurl` plus
serialized internal URLs using its matching WP-CLI. Review embedded production
widgets/callbacks. Restore routes only to the local test databases. Keep all
networks internal throughout the rehearsal. Start only the reviewed services with
the generated Compose files; leave ERP workers/scheduler stopped until verified.
Record SQL/table counts, app record counts, authenticated UI checks, a second
backup/restore round-trip and a host reboot under #22.

Earlier migration-only archives and the November 10 pre-repair snapshot cannot
prove complete full-stack recovery. Use the repaired nightly job and a new
format-2 snapshot. Installed LibreChat/WordPress/scheduling groups require their
complete data; an empty fresh install cannot substitute for a missing payload.

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

## Internal service routing (production and test deployments)

Use Docker Compose service DNS and container ports for **server-to-server calls** between RootedOps services on the same Compose network. Do not route those requests through the public NGINX hostname or another deployment's `-test` host. Public HTTPS addresses remain necessary for browser navigation, OAuth redirects, webhook ingress, email links, and Appsmith page links. Never indiscriminately rewrite all URLs.

| Calling service | Internal destination | Public-facing counterpart |
| --- | --- | --- |
| n8n to NocoDB API | `http://nocodb:8080` | `NC_PUBLIC_URL` for browser links |
| n8n to Documenso API | `http://documenso:3000` | `DOCUMENSO_PUBLIC_URL` for users/callbacks |
| n8n to Listmonk API | `http://listmonk:9000` (`LISTMONK_API_BASE_URL`) | `LISTMONK_PUBLIC_URL` for email/user links |
| n8n to ERPNext API | `http://erpnext-backend:8000` (`ERPNEXT_INTERNAL_URL`) | `ERPNEXT_PUBLIC_URL` |
| Appsmith to n8n | `http://n8n:5678` for server-executed API datasources | `WEBHOOK_URL`/editor URL for external callbacks/browser links |

Appsmith API datasources, n8n workflow nodes and credentials can store URLs **in restored application data**, not in Compose environment variables. An environment-level change does **not** rewrite them. Inventory those saved destinations, classify whether a request executes server-side or in the browser, and migrate only same-network API requests. Preserve query strings, credentials, workflow IDs and public callback/link URLs. If services are in distinct Compose projects or networks, DNS service names alone will not resolve; explicitly provision and validate a dedicated shared internal network before using them. No automatic production migration or test2 application startup is authorized by these defaults.

For test2, update only generated `.test-deployment/core.yml` n8n server-side URL values after recording a private backup. Validate Compose and the internal network, audit restored Appsmith/n8n connections, and keep background automation disabled during acceptance.

## Test2 scheduling restore closeout (2026-11-03)

The clean-Linode test2 exercise used the original 2026-10-30 02:30:01 backup
at `~/backups/20261030-023001`. `sha256sum -c SHA256SUMS` passed,
including both Tymeslot volumes and the three Rallly PostgreSQL/Garage volumes.
Restoration into separate `tymeslot-test_*` and `rallly-test_*` volumes
was already complete; **never rerun a destructive volume extraction against
those populated volumes**. The database versions on disk were Tymeslot
PostgreSQL 17 (`pgdata/PG_VERSION`) and Rallly PostgreSQL 18
(`18/docker/PG_VERSION`). Both Tymeslot data encryption values and the five
reviewed Rallly storage/DB secrets matched their private source backup.
No secrets should be printed or copied into published host configuration.

The isolated generated Compose files validated with internal-only networks and
loopback-only declared/preserved host bindings. Tymeslot 1.6.0 recognized its
restored DB, completed migrations and started Phoenix; an in-network HTTP GET
at `http://tymeslot:4000/` served an HTML page. Its SMTP probe could not
resolve `mailpit` because the separate local sink was not running; do not
switch to production SMTP for acceptance. Start the isolated test Mailpit service
if email-sink validation is ever required.

Rallly PostgreSQL 18 and Garage v2.3.0 started and were healthy; Garage opened
its restored SQLite metadata. Rallly web v4 found 166 migrations with none
pending. Initially the web failed validation due to a missing `SUPPORT_EMAIL`.
Generated test Rallly environment now supplies `SUPPORT_EMAIL=support@example.invalid`.
After a test-only manual addition, the web container started, but in-network
`http://web:3000/` returned HTTP 500. This remains **unaccepted** application
recovery and should be inspected for a specific runtime error in private logs
before any future full-stack acceptance claim. No restored poll-level data check
or authenticated scheduling journey was completed.

A host `curl` to 127.0.0.1:4000 or 127.0.0.1:3003 returned connection refused
although Docker HostConfig reported correct loopback port bindings. Docker
`compose ps` displaying `4000/tcp` / `3000/tcp` alone does not establish
missing bindings. Prefer in-network HTTP probes for recovery diagnosis, then
separately debug host-network access if public ingress is needed. In-network
probes must not be treated as proof of external DNS/TLS routing.

The SSH session dropped during the operator exercise. Shell variables/Compose
arrays did not persist across reconnect, so subsequent shell commands on the
operator's local Mac did **not** inspect or stop test2. Always confirm hostname,
`TEST_ENVIRONMENT`, and restore-specific Compose project before commands;
reconstruct shell variables after reconnect. Private evidence was saved at
`~/test2-closeout-20261103-203604`; scheduling service stop and any final
shutdown must be checked on the **test2 Linode**, not the local workstation.

This is a documented partial full-stack restore rehearsal, not proof that
LibreChat, every WordPress/scheduling service, public DNS/TLS, reboot or backup
round-trip were fully accepted. Future recovery work must explicitly verify
these if required; do not reuse production OAuth/SMTP/payment credentials or
run the unrestricted production `backup/restore-stack.sh` on test2.
