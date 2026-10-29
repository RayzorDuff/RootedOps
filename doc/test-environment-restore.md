# Fresh Linode test recovery

Use a **fresh Ubuntu 24.04** Linode. Production remains 45.33.107.185;
45.33.13.190 is the authorized current test host. This procedure does not rebuild
or overwrite the already-used `commerce-test` project. Use a fresh Linode for a
full rehearsal, or retain the existing host for incremental development.

## Provision, render, build

```bash
git clone https://github.com/RayzorDuff/RootedOps.git /opt/RootedOps
cd /opt/RootedOps
# Until merged: git switch feat/commerce-foundation
sudo bash linode_bootstrap.sh
sudo python3 scripts/commerce_staging.py /opt/commerce-test
sudo docker compose --env-file /opt/commerce-test/.env -f /opt/commerce-test/compose.yml config --quiet
sudo docker compose --env-file /opt/commerce-test/.env -f /opt/commerce-test/compose.yml build erpnext-backend
```

The bootstrap installs Docker/Compose, NGINX/Certbot, PostgreSQL client, PyYAML,
rclone and the encrypted-transfer dependency. It opens only SSH/HTTP/HTTPS in
UFW. Every rendered Docker port binds to loopback because Docker can bypass UFW.
No services or certificates are provisioned automatically. The renderer creates
fresh credentials and a `TEST_ENVIRONMENT` marker, and refuses overwrites.
Only PostgreSQL, Appsmith, n8n and ERPNext dependencies are selected. No Minecraft,
listmonk, scheduling or Rooted Psyche instance is launched. The separate Dank
WordPress file remains opt-in, loopback port 8097, with independent credentials.

## Recover selected data before starting apps

Securely obtain a complete verified backup in `/opt/backup` with this layout:

- `db/mushroomprocess-bridge-postgres.sql.gz`
- `db/erpnext-all-databases.sql.gz` if restoring ERPNext
- `volumes/n8n_data.tgz`, `volumes/appsmith_stacks.tgz`
- `volumes/erpnext_sites.tgz` if restoring ERPNext (contains private files/keys)
- `meta/.env` if restoring n8n (original `N8N_ENCRYPTION_KEY` is required)
- `SHA256SUMS` from the full backup, when available

Never commit these files. Directory mode 0700, files 0600. Do not load the
production `.env` into staging. Only n8n's encryption key is recovered from it.
All selected gzip streams and volume archives are validated before mutation;
empty Appsmith/n8n archives are rejected. Full-backup checksum manifests must
accompany the complete directory; do not pass a subset with stale checksums.

```bash
cd /opt/RootedOps
# Source site name must match the directory inside erpnext_sites.tgz.
sudo python3 scripts/commerce_restore.py /opt/commerce-test /opt/backup \
  --components mushroomprocess n8n appsmith erpnext --source-site erp.danks.store
```

For the supplied PostgreSQL backup alone, stage it at the `db/` path above and
select `--components mushroomprocess`. The supplied Appsmith/n8n archives contain
no files and cannot restore those applications. A new production backup is needed.
ERPNext data was not supplied in these attachments.

The restore refuses existing project containers and nonempty target app volumes.
It uses actual mounts from the generated containers, starts only selected database
services, and streams SQL with error checking. On failure it leaves a
`RESTORE_STARTED` marker and partial data for inspection; it never silently clears
volumes or retries. Do not rerun on a partially restored environment.

ERP recovery retains source document encryption keys, imports only the source
site's MariaDB database with `--one-database` (not system users), creates a fresh
site DB password, renames the site to **erp-test.danks.store**, replaces global
DB/Redis connection settings, and enables maintenance mode/pauses scheduling.
It uses application code from the new image, not the backed-up apps volume.
Build the image with Frappe/ERPNext/HRMS/ESS versions matching the backup first;
the floating version-16 default is not an exact production pin. Record image
digests and source app versions from backup metadata before accepting recovery.
Run `bench --site erp-test.danks.store migrate` only after reviewing compatibility.

Applications remain stopped. Before starting n8n, disable every restored workflow
using its version-matched CLI and review credentials/production endpoints. Before
starting Appsmith, replace restored datasource connections with test PostgreSQL.
Before starting ERP workers, disable outbound email, webhooks and scheduled jobs
and review integrations. Keep maintenance mode enabled until that review completes.
Never start the whole Compose project indiscriminately after a production restore.

## Explicit default hostnames

Every checked-in NGINX vhost now names a test host, including optional services:

| Configuration | Host | Loopback port |
| --- | --- | --- |
| erpnext.conf | erp-test.danks.store | 8086 |
| appsmith.conf | appsmith-test.danks.store | 8081 |
| n8n.conf | n8n-test.danks.store | 5678 |
| dank-wordpress.conf | shop-test.danks.store | 8097 |
| nocodb.conf | nocodb-test.danks.store | 8080 |
| documenso.conf | documenso-test.danks.store | 3002 |
| listmonk.conf | listmonk-test.danks.store | 9000 |
| grav.conf | grav-test.danks.store | 8085 |
| librechat.conf | ai-test.danks.store | 3080 |
| kids-ai.conf | kids-ai-test.danks.store | 3081 |
| qr.conf | qr-test.danks.store | n8n resolver |
| tymeslot.conf | schedule-test.danks.store | 4000 |
| rallly.conf | poll-test.danks.store | 3003 |

Only the first four DNS records are confirmed created by the operator. Optional
hostnames do not imply DNS exists or services have been deployed/tested. Existing
production hostnames and installed NGINX files are not modified by this change.

Enable only reviewed applications after their setup/accounts and data are secured.
For example, once the test ERP is ready:

```bash
sudo cp nginx/erpnext.conf /etc/nginx/sites-available/erpnext.conf
sudo ln -sfn /etc/nginx/sites-available/erpnext.conf /etc/nginx/sites-enabled/erpnext.conf
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d erp-test.danks.store
sudo certbot renew --dry-run
```

Use `appsmith.conf`, `n8n.conf` and `dank-wordpress.conf` with their exact test
hostnames as those services become ready. Do not expose unclaimed setup wizards.
Certbot requires public DNS to this host and ports 80/443 reachable. The current
user has authorized test-host certificate installation; production is excluded.

## Evidence and remaining acceptance

Local unit tests cover rendering, isolation, malformed/missing archives and
hostname defaults. CI exercises a real PostgreSQL 16 dump/restore and refusal of
an existing project. This does not substitute for restoring the actual attached
backup natively or an end-to-end ERP/Appsmith/n8n restore. The current browser
Linode session expired before the newly approved certificate installation;
renewed access is required to finish those live checks. No new certificate is
claimed provisioned. The earlier complete attached dump restore was supplemental
PGlite validation; see `commerce-staging.md` for its measured counts/limits.
