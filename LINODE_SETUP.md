# Linode setup (Linux)

This is intentionally high-level and points you to upstream docs where appropriate.

## 0. Provision
- Ubuntu 22.04/24.04 LTS
- Enable backups, add an SSH key, disable password SSH.
- Size the Linode for the combined workload. With Appsmith, NocoDB, Documenso, Grav, PostgreSQL, MariaDB, Redis, and ERPNext/Frappe HR on one host, start closer to an 8 GB / 4 vCPU plan than a minimal instance.

## 1. Baseline hardening
- Create non-root user, add to sudo
```bash
useradd -m signaturegate
passwd signaturegate
usermod -aG sudo signaturegate
```
- Configure UFW: allow 22, 80, 443
```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw --force enable
```
- Install fail2ban and base tooling
```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg ufw fail2ban git jq mariadb-client postgresql-client python3 python3-dotenv-cli
```
- Keep system updated

## 2. Install Docker
Follow Docker’s official instructions for Ubuntu:
https://docs.docker.com/engine/install/ubuntu/

## 3. Deploy the base SignatureGate stack
```bash
su - signaturegate
ssh-keygen -t ed25519 -C "your@email.com"
cat ~/.ssh/id_ed25519.pub   # add for repository access if needed
git clone git@github.com/RayzorDuff/SignatureGate.git signaturegate
cd signaturegate
cp .env.example .env
nano .env
```

Fill in all existing secrets, then also set the ERPNext section at the bottom of `.env`:

- `ERPNEXT_PUBLIC_URL=https://erpnext.yourdomain.com`
- `ERPNEXT_DB_ROOT_PASSWORD`
- `ERPNEXT_ADMIN_PASSWORD`
- `ERPNEXT_HRMS_BRANCH=version-16`

Start the long-running services:

```bash
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml up -d
sudo docker ps
```

## 4. Bootstrap ERPNext + Frappe HR (one time)

ERPNext runs in the official `frappe/erpnext` container family, while payroll and HR features come from the separate Frappe HR / HRMS app. Run the one-time bootstrap service after the main compose stack is up.

```bash
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml --profile erpnext-init up erpnext-bootstrap
```

That bootstrap service will:

- wait for MariaDB and Redis
- create the initial ERPNext site if it does not already exist
- fetch the HRMS app into the persistent ERPNext apps volume
- install HRMS on the ERPNext site
- set `host_name` to `ERPNEXT_PUBLIC_URL`
- run a final migrate

Re-running the bootstrap command is safe; it is written to be idempotent.

### Useful ERPNext checks
```bash
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml logs -f erpnext-bootstrap
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml exec erpnext-backend bench --site "$ERPNEXT_SITE_NAME" list-apps
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml exec erpnext-backend bench --site "$ERPNEXT_SITE_NAME" doctor
```

Expected installed apps after bootstrap:
- `erpnext`
- `hrms`

## 5. NGINX reverse proxy + TLS

This repo includes example NGINX site configs under:

- `deploy/nginx/n8n.conf`
- `deploy/nginx/nocodb.conf`
- `deploy/nginx/appsmith.conf`
- `deploy/nginx/documenso.conf`
- `deploy/nginx/grav.conf`
- `deploy/nginx/erpnext.conf`

Install them like this:

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp deploy/nginx/*.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/n8n.conf /etc/nginx/sites-enabled/n8n.conf
sudo ln -sf /etc/nginx/sites-available/nocodb.conf /etc/nginx/sites-enabled/nocodb.conf
sudo ln -sf /etc/nginx/sites-available/appsmith.conf /etc/nginx/sites-enabled/appsmith.conf
sudo ln -sf /etc/nginx/sites-available/documenso.conf /etc/nginx/sites-enabled/documenso.conf
sudo ln -sf /etc/nginx/sites-available/grav.conf /etc/nginx/sites-enabled/grav.conf
sudo ln -sf /etc/nginx/sites-available/erpnext.conf /etc/nginx/sites-enabled/erpnext.conf
sudo nginx -t
sudo systemctl reload nginx
```

Issue certificates (example):

```bash
sudo certbot --nginx   -d n8n.yourdomain.com   -d nocodb.yourdomain.com   -d appsmith.yourdomain.com   -d documenso.yourdomain.com   -d erpnext.yourdomain.com   -d yourdomain.com   -d www.yourdomain.com
```

After DNS and certificates are in place, verify:

```bash
curl -I http://localhost:8086
curl -I https://erpnext.yourdomain.com
```

## 6. Documenso (self-hosted signing)

Documenso runs as a Docker container exposed on localhost port `3002` (proxied by NGINX).

### 6.1 Configure environment variables
Edit `.env` and set:

- `DOCUMENSO_PUBLIC_URL=https://documenso.yourdomain.com`
- `DOCUMENSO_NEXTAUTH_SECRET` (random)
- `DOCUMENSO_ENCRYPTION_KEY` (random)
- `DOCUMENSO_ENCRYPTION_SECONDARY_KEY` (random)
- `DOCUMENSO_SIGNING_PASSPHRASE` (random but memorable)
- SMTP settings (`DOCUMENSO_SMTP_*`)

Documenso needs SMTP to send signing links.

### 6.2 Create the signing certificate file
Documenso expects a `.p12` file mounted at `deploy/documenso/certs/cert.p12`.

Create the folder:

```bash
mkdir -p deploy/documenso/certs
```

Start the stack (Documenso + its Postgres):

```bash
sudo touch deploy/documenso/certs/cert.p12
sudo chmod 644 deploy/documenso/certs/cert.p12
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml up -d documenso-postgres documenso
```

Generate a self-signed `.p12` inside the container:

```bash
read -s -p "Enter Documenso cert passphrase (DOCUMENSO_SIGNING_PASSPHRASE): " CERT_PASS
echo
sudo docker exec -e CERT_PASS="$CERT_PASS" -it documenso openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /tmp/private.key -out /tmp/certificate.crt -subj '/C=US/ST=Colorado/L=Denver/O=SignatureGate/CN=documenso'
sudo docker exec -e CERT_PASS="$CERT_PASS" -it documenso openssl pkcs12 -export -legacy -out /opt/documenso/cert.p12 -inkey /tmp/private.key -in /tmp/certificate.crt -passout env:CERT_PASS
sudo docker exec -it documenso rm /tmp/private.key /tmp/certificate.crt
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml restart documenso
```

### 6.3 Verify
- Documenso should be reachable at `https://documenso.yourdomain.com`
- Health endpoint from the Linode:
  - `curl http://localhost:3002/api/health`

If Documenso documents get stuck in “Processing document…” after both recipients sign, see:
- `deploy/DOCUMENSO_CERT_TROUBLESHOOTING.md`

## 7. Grav

Launch Grav if it is not already running:
```bash
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml up -d grav
```

Configure Grav at `http://localhost:8085/admin`, then point your browser to `https://www.yourdomain.com`.

## 8. Backups
- Nightly database dumps for:
  - SignatureGate Postgres
  - MushroomProcess bridge Postgres
  - NocoDB metadata Postgres
  - Documenso Postgres
  - ERPNext MariaDB
- Snapshot Docker volumes regularly.
- Back up `erpnext_sites`, `erpnext_apps`, and `erpnext_logs` alongside database dumps.
- Store signed documents and other evidence files in durable off-server storage.

### Example ERPNext backup commands
```bash
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml exec erpnext-backend bench --site "$ERPNEXT_SITE_NAME" backup --with-files
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml exec erpnext-db mariadb-dump -uroot -p"$ERPNEXT_DB_ROOT_PASSWORD" --all-databases > erpnext-all.sql
```

## 9. Operational notes
- Use ERPNext Companies for both Dank Mushrooms and Rooted Psyche inside one ERPNext site unless you later decide you need strict application-level separation.
- Keep SignatureGate / MushroomProcess application databases separate from ERPNext. Integration should happen through APIs, exports, or controlled ETL, not shared tables.
- ERPNext and Frappe HR are resource-hungry compared with Grav or n8n; monitor memory pressure closely after enabling payroll and background jobs.
