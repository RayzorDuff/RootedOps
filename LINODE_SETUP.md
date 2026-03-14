# Linode setup (Linux)

This guide now assumes RootedOps is the standalone infrastructure repository. Commands below use the RootedOps repository root, where `.env` lives at the top level and the compose file lives at `docker/docker-compose.yml`.

This is intentionally practical rather than exhaustive. It assumes Ubuntu 22.04 or 24.04 on a single Linode running the full RootedOps stack from this repository.

## 0. Provision
- Ubuntu 22.04/24.04 LTS
- Enable Linode backups.
- Add an SSH key during provisioning and disable password SSH.
- Size the Linode for the combined workload. With Appsmith, NocoDB, Documenso, Grav, PostgreSQL, MariaDB, Redis, n8n, and ERPNext/Frappe HR on one host, start closer to an 8 GB / 4 vCPU plan than a minimal instance.
- Add a DNS A record for each subdomain you intend to proxy.

## 1. Baseline hardening
- Create a non-root user and add it to sudo:

```bash
sudo useradd -m rootedops
sudo passwd rootedops
sudo usermod -aG sudo rootedops
```

- Configure UFW:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8080/tcp
sudo ufw --force enable
```

- Install base tooling:

```bash
sudo apt-get update
sudo apt-get install -y \
  ca-certificates \
  curl \
  fuse3 \
  git \
  gnupg \
  jq \
  mariadb-client \
  postgresql-client \
  python3 \
  python3-dotenv-cli \
  tar \
  unzip \
  ufw \
  fail2ban
```

- Keep the system patched.

## 2. Install Docker
Follow Docker's official Ubuntu instructions.

## 3. Deploy the base RootedOps stack

```bash
su - rootedops
ssh-keygen -t ed25519 -C "your@email.com"
cat ~/.ssh/id_ed25519.pub
# add the key for repository access if needed

git clone git@github.com/RayzorDuff/RootedOps.git rootedops
cd rootedops
cp .env.example .env
nano .env
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d
sudo docker ps
```

## 4. Add TLS + reverse proxy (recommended)

This repo includes example NGINX site configs under:
- `nginx/n8n.conf`
- `nginx/nocodb.conf`
- `nginx/appsmith.conf`
- `nginx/documenso.conf`
- `nginx/grav.conf`
- `nginx/erpnext.conf`

Install them like this:

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp nginx/*.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/n8n.conf /etc/nginx/sites-enabled/n8n.conf
sudo ln -sf /etc/nginx/sites-available/nocodb.conf /etc/nginx/sites-enabled/nocodb.conf
sudo ln -sf /etc/nginx/sites-available/appsmith.conf /etc/nginx/sites-enabled/appsmith.conf
sudo ln -sf /etc/nginx/sites-available/documenso.conf /etc/nginx/sites-enabled/documenso.conf
sudo ln -sf /etc/nginx/sites-available/grav.conf /etc/nginx/sites-enabled/grav.conf
sudo ln -sf /etc/nginx/sites-available/erpnext.conf /etc/nginx/sites-enabled/erpnext.conf
sudo nginx -t
sudo systemctl reload nginx
```

Then request certificates:

```bash
sudo certbot --nginx \
  -d n8n.yourdomain.com \
  -d nocodb.yourdomain.com \
  -d appsmith.yourdomain.com \
  -d documenso.yourdomain.com \
  -d erp.yourdomain.com \
  -d www.yourdomain.com \
  -d yourdomain.com
```

Update `.env` values so each service knows its public URL.

## 5. Persistent data map in this stack

Before defining backups, it helps to identify what actually needs to be preserved.

### Databases
- `signaturegate-postgres` → `signaturegate_pgdata`
- `mushroomprocess-bridge-postgres` → `mushroomprocess_bridge_pgdata`
- `nocodb-meta-postgres` → `nocodb_meta_pgdata`
- `documenso-postgres` → `documenso_pgdata`
- `erpnext-db` (MariaDB) → `erpnext_db_data`

### Non-database Docker volumes to preserve
- `nocodb_data` → NocoDB app data and uploads
- `n8n_data` → n8n config, credentials, workflows, encryption state
- `appsmith_stacks` → Appsmith persistent data
- `erpnext_sites` → ERPNext sites and uploaded files
- `erpnext_apps` → ERPNext apps volume initialized from the custom image
- `erpnext_logs` → ERPNext logs

### Usually disposable volumes
- `erpnext_redis_cache_data`
- `erpnext_redis_queue_data`

These Redis volumes can still be backed up if you want a more literal snapshot, but they are not usually required for a clean restore.

### Bind-mounted paths to preserve
- `documenso/certs/cert.p12`
- `grav/`
- `.env`
- `nginx/`

## 6. Documenso (self-hosted signing)

Documenso runs as a Docker container exposed on localhost port `3002` and proxied by NGINX.

### 6.1 Configure environment variables
Set these in `.env`:
- `DOCUMENSO_PUBLIC_URL=https://documenso.yourdomain.com`
- `DOCUMENSO_NEXTAUTH_SECRET`
- `DOCUMENSO_ENCRYPTION_KEY`
- `DOCUMENSO_ENCRYPTION_SECONDARY_KEY`
- `DOCUMENSO_SIGNING_PASSPHRASE`
- `DOCUMENSO_SMTP_*`

Documenso needs SMTP to send signing links.

### 6.2 Build documenso
The documenso docker container must be built.  After the build, the build artifacts and cache may 
be deleted to free up space.

If this is a rebuild, then clean up and remove the old documenso
```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml stop documenso
sudo docker system df -v | grep -i gb # Identify the large image
sudo docker images | grep documenso
sudo docker rmi docker-documenso:latest # Or reference the id of the large image(s)
sudo docker builder prune -a
```

Once the old documenso is removed or if this is a new installation, first build the image

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml  build --no-cache documenso
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up documenso
```

If the schema has been updated you may need to perform migrations

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml run --rm documenso sh -lc "cd /app/packages/prisma && npx prisma migrate deploy"
```

Launch all images before pruning the system

```bash
df -h
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up
sudo docker image prune -a
sudo docker builder prune -a
df -h
```

### 6.3 Create the signing certificate file
Documenso expects a `.p12` file mounted at `documenso/certs/cert.p12`.

```bash
mkdir -p documenso/certs
sudo touch documenso/certs/cert.p12
sudo chmod 644 documenso/certs/cert.p12
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d documenso-postgres documenso
```

Generate a self-signed `.p12` inside the container:

```bash
read -s -p "Enter Documenso cert passphrase (DOCUMENSO_SIGNING_PASSPHRASE): " CERT_PASS
echo
sudo docker exec -e CERT_PASS="$CERT_PASS" -it documenso \
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /tmp/private.key \
    -out /tmp/certificate.crt \
    -subj '/C=US/ST=Colorado/L=Denver/O=RootedOps/CN=documenso'

sudo docker exec -e CERT_PASS="$CERT_PASS" -it documenso \
  openssl pkcs12 -export -legacy -out /opt/documenso/cert.p12 \
    -inkey /tmp/private.key \
    -in /tmp/certificate.crt \
    -passout env:CERT_PASS

sudo docker exec -it documenso rm /tmp/private.key /tmp/certificate.crt
sudo docker compose --env-file ./.env -f docker/docker-compose.yml restart documenso
```

### 6.4 Verify
- `curl http://localhost:3002/api/health`
- Sign a test document end to end.

If signed documents get stuck in `Processing document...`, inspect the Documenso container logs and verify the mounted `documenso/certs/cert.p12` file and passphrase.

## 7. Grav

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d grav
```

Admin UI:
- `http://localhost:8085/admin`

Then complete the NGINX and Certbot steps for your main site.

## 8. ERPNext + Frappe HR

This repository builds a custom ERPNext image that includes HRMS at image build time.

### 8.1 Configure environment
Set these in `.env`:
- `ERPNEXT_PUBLIC_URL=https://erp.yourdomain.com`
- `ERPNEXT_SITE_NAME=erp.yourdomain.com`
- `ERPNEXT_DB_ROOT_PASSWORD`
- `ERPNEXT_ADMIN_PASSWORD`
- `ERPNEXT_HRMS_BRANCH=version-16`

### 8.2 Build and start ERPNext services

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml build erpnext-backend
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d \
  erpnext-db \
  erpnext-redis-cache \
  erpnext-redis-queue \
  erpnext-apps-init \
  erpnext-configurator \
  erpnext-backend \
  erpnext-websocket \
  erpnext-queue-short \
  erpnext-queue-long \
  erpnext-scheduler \
  erpnext-frontend
```

### 8.3 Initialize the site

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml --profile erpnext-init up erpnext-bootstrap
```

## 9. Mount Google Drive on the Linode for off-host backups

The backup plan below assumes a mounted Google Drive path such as `/mnt/google-drive`.

### 9.1 Install rclone

```bash
sudo -v
curl https://rclone.org/install.sh | sudo bash
rclone version
```

### 9.2 Configure a Google Drive remote
Run the interactive setup under the deployment user:

```bash
su - rootedops
rclone config
```

Recommended choices:
- New remote name: `rootedops-gdrive`
- Storage type: `drive`
- Scope: usually full drive access for a dedicated backup destination
- Use auto config if you have a browser available; otherwise follow the headless flow

Confirm the remote works:

```bash
rclone lsd rootedops-gdrive:
```

### 9.3 Create local mount directories

```bash
sudo mkdir -p /mnt/google-drive
sudo chown rootedops:rootedops /mnt/google-drive
mkdir -p /home/rootedops/.cache/rclone
mkdir -p /home/rootedops/.local/state
```

### 9.4 Ensure allow-other is enabled 

/etc/fuse.conf must contain the user_allow_other

```bash
sudo vim /etc/fuse.conf
```

### 9.5 Ensure local user can use sudo without password

```bash
sudo visudo
rootedops ALL=(ALL) NOPASSWD: ALL
```

### 9.6 Install the example systemd unit
The repo includes `backup/rclone-gdrive.service.example`.

Install it as root:

```bash
sudo cp backup/rclone-gdrive.service.example /etc/systemd/system/rclone-gdrive.service
sudo systemctl daemon-reload
sudo systemctl enable --now rclone-gdrive.service
```

Verify the mount:

```bash
mount | grep google-drive
ls -la /mnt/google-drive
```

### 9.7 Notes
- The mount runs as the `rootedops` user.
- If you change the remote name, mount path, or username, update the service file.
- If the service fails at boot, inspect:

```bash
sudo systemctl status rclone-gdrive.service
journalctl -u rclone-gdrive.service -n 100 --no-pager
```

## 10. Automated backups to the mounted Google Drive

This repo now includes two helper scripts:
- `backup/backup-stack.sh`
- `backup/restore-stack.sh`

### 10.1 What the backup script does
`backup-stack.sh` now stages each backup on the local filesystem first, then uploads it to Google Drive with `rclone`, then deletes the local staged copy.

The staged backup contains:
- Logical SQL dumps for all Postgres and MariaDB databases
- Tar archives of the important non-database Docker volumes
- Tar archives of bind-mounted directories and certificate files
- Copies of `.env` and `docker/docker-compose.yml`
- A SHA-256 manifest for integrity checking
- A `latest` symlink pointing to the newest timestamped backup directory

Suggested defaults used by the script:

```text
LOCAL_STAGING_PARENT=/var/tmp/rootedops-backups
RCLONE_REMOTE=rootedops-gdrive
REMOTE_BACKUP_ROOT=rootedops-gdrive:RootedOpsBackups
BACKUP_PREFIX=rootedops
```

The local staging layout looks like this during the run:

```text
/var/tmp/rootedops-backups/<random>/
├── 20260313-023000/
└── latest -> 20260313-023000
```

The script then uploads that staged tree with:

```bash
rclone copy --links "$LOCAL_STAGE_ROOT/" "$REMOTE_BACKUP_ROOT/$BACKUP_PREFIX/"
```

With `--links`, rclone translates symlinks to and from regular files with a `.rclonelink` extension rather than requiring native symlink support on the remote. That means the `latest` pointer can round-trip through Google Drive even though Google Drive does not natively store Unix symlinks. citeturn328202view0

After upload, the script applies retention on the remote backup set:
- keep **all** backups from the last 7 days
- for older backups in the **current month**, keep only the newest backup from each ISO week
- for backups from **earlier months**, keep only the newest backup from each calendar month

Then it removes the local staged backup directory.

### 10.2 Run a manual test backup first

```bash
cd ~/rootedops
bash backup/backup-stack.sh
```

Inspect the remote backup set:

```bash
rclone lsf rootedops-gdrive:RootedOpsBackups/rootedops/
```

If you also keep the Google Drive mounted, you can inspect it there too. The `latest` link will be represented remotely via rclone link translation, not as a native Google Drive symlink. citeturn328202view0

### 10.3 Install the nightly cron job
Edit the crontab for the deployment user:

```bash
crontab -e
```

Recommended nightly job at 2:30 AM local time:

```cron
30 2 * * * cd /home/rootedops/rootedops && /usr/bin/bash backup/backup-stack.sh >> /home/rootedops/.local/state/rootedops-backup.log 2>&1
```

Optional environment overrides for the cron job:

```cron
30 2 * * * cd /home/rootedops/rootedops && LOCAL_STAGING_PARENT=/var/tmp/rootedops-backups RCLONE_REMOTE=rootedops-gdrive REMOTE_BACKUP_ROOT=rootedops-gdrive:RootedOpsBackups /usr/bin/bash backup/backup-stack.sh >> /home/rootedops/.local/state/rootedops-backup.log 2>&1
```

### 10.4 Recommended backup validation routine
At least once before trusting the backups, perform a real restore test on a second Linode or disposable VM.

## 11. Restore procedure on a fresh deployment

The cleanest restore path is:
1. Provision a fresh Linode.
2. Install Docker, rclone, NGINX, and the base packages.
3. Clone this repository.
4. Restore `.env` from your backup.
5. Bring up only the database containers and restore database dumps.
6. Restore non-database volumes and bind mounts.
7. Start the full stack.

### 11.1 Fresh host preparation

```bash
git clone git@github.com/RayzorDuff/RootedOps.git rootedops
cd rootedops
```

Restore `.env` from the backup before running compose.

### 11.2 Retrieve the desired backup set
You can restore either from the mounted Google Drive path or by using `rclone` directly.

Using `rclone` directly is often cleaner on a fresh host because it recreates the `latest` symlink correctly when `--links` is used:

```bash
mkdir -p /tmp/rootedops-restore
rclone copy --links rootedops-gdrive:RootedOpsBackups/rootedops/20260313-023000 /tmp/rootedops-restore/20260313-023000
```

If you want to restore the remote `latest` pointer too, you can also copy the whole prefix instead:

```bash
mkdir -p /tmp/rootedops-restore-prefix
rclone copy --links rootedops-gdrive:RootedOpsBackups/rootedops /tmp/rootedops-restore-prefix
ls -l /tmp/rootedops-restore-prefix/latest
```

### 11.3 Run the restore helper

```bash
cd ~/rootedops
bash backup/restore-stack.sh /tmp/rootedops-restore/20260313-023000
```

What the restore helper does:
- Verifies checksums if `SHA256SUMS` is present
- Restores the non-database Docker volumes
- Restores `documenso/certs`, `grav`, and `nginx`
- Starts only the database containers
- Imports the Postgres and MariaDB dumps

### 11.4 Start the full stack

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d
```

### 11.5 Post-restore validation
Check each service directly:

```bash
sudo docker ps
curl -I http://localhost:8080
curl -I http://localhost:8081
curl -I http://localhost:3002/api/health
curl -I http://localhost:8085
curl -I http://localhost:5678
curl -I http://localhost:8086
```

Then validate in the UI:
- NocoDB tables and attachments
- n8n workflows and credentials
- Appsmith applications
- Documenso login and completed documents
- Grav content and admin login
- ERPNext site, attachments, and HRMS

## 12. Backup/restore caveats and recommendations

- Do not rely on Docker images as your primary backup. Re-pull or rebuild images from code and preserve data separately.
- Database dumps are more portable than raw database volume archives.
- ERPNext file uploads live in `erpnext_sites`, so keep that archive alongside the MariaDB dump.
- NocoDB uploads live in `nocodb_data`, so do not treat NocoDB as database-only.
- Keep `.env` secure. It contains credentials and secrets required for restore.
- Periodically prune old Docker build cache only after you have a known-good backup and restore procedure.

## 13. Next steps

### ERPNext Operational notes
- Use ERPNext Companies for both Dank Mushrooms and Rooted Psyche inside one ERPNext site unless you later decide you need strict application-level separation.
- Keep SignatureGate and MushroomProcess application databases separate from ERPNext. Integration should happen through APIs, exports, or controlled ETL, not shared tables.
- ERPNext and Frappe HR are resource-hungry compared with Grav or n8n; monitor memory pressure closely after enabling payroll and background jobs.

### Repository boundary

RootedOps provides the Linode infrastructure. SignatureGate is an Appsmith application layer with a PostgreSQL schema that can run on top of that infrastructure, and MushroomProcess may do the same with its own databases and services.

This repository is that separate infrastructure project required by SignatureGate and MushroomProcess. SignatureGate and MushroomProcess should reference RootedOps for deployment architecture rather than carrying host-level infrastructure in their own repositories.
