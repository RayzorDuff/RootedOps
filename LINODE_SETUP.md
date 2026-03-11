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
- Configure UFW: allow 22, 80, 443, 8080
```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 8080/tcp && sudo ufw --force enable
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
# edit secrets in .env
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml up -d
sudo docker ps
sudo docker logs nocodb
```

## 4. Add TLS + reverse proxy (recommended)

## 4a. Use the provided NGINX site configs (recommended)

This repo includes example NGINX site configs under:

- `deploy/nginx/n8n.conf`
- `deploy/nginx/nocodb.conf`
- `deploy/nginx/appsmith.conf`
- `deploy/nginx/documenso.conf`
- `deploy/nginx/grav.conf`

Install them like this:

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp deploy/nginx/*.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/n8n.conf /etc/nginx/sites-enabled/n8n.conf
sudo ln -sf /etc/nginx/sites-available/nocodb.conf /etc/nginx/sites-enabled/nocodb.conf
sudo ln -sf /etc/nginx/sites-available/appsmith.conf /etc/nginx/sites-enabled/appsmith.conf
sudo ln -sf /etc/nginx/sites-available/documenso.conf /etc/nginx/sites-enabled/documenso.conf
sudo ln -sf /etc/nginx/sites-available/grav.conf /etc/nginx/sites-enabled/grav.conf
sudo nginx -t
sudo systemctl reload nginx
```

Then issue certificates (example):

```bash
sudo certbot --nginx -d n8n.yourdomain.com -d nocodb.yourdomain.com -d appsmith.yourdomain.com -d documenso.yourdomain.com -d www.yourdomain.com -d yourdomain.com
```

Set up NGINX as a reverse proxy.  Change n8n.yourdomain.com to match your server name.

```bash
sudo nano /etc/nginx/sites-available/n8n.conf

server {
    listen 80;
    server_name n8n.yourdomain.com;

    location / {
        proxy_pass http://localhost:5678/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable NGINX and restart
```bash
sudo ln -s /etc/nginx/sites-available/n8n.conf /etc/nginx/sites-enabled/n8n.conf
sudo nginx -t # Test the configuration for syntax errors
sudo systemctl restart nginx
```
Ensure your DNS is configured correctly and obtain an SSL Certificate with certbot
```bash
sudo certbot --nginx -d n8n.yourdomain.com
```

Configure your .env 
```bash
N8N_HOST=n8n.yourdomain.com
N8N_PORT=5678
N8N_PROTOCOL=https
WEBHOOK_URL=https://n8n.yourdomain.com/
```

Reload n8n
```bash
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml up -d
```
You may do the same for Appsmith (appsmith.yourdomain.com) and NocoDB (nocodb.yourdomain.com)

## 5. Backups
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

Generate a self-signed `.p12` inside the container (recommended by Documenso):

```bash
read -s -p "Enter Documenso cert passphrase (DOCUMENSO_SIGNING_PASSPHRASE): " CERT_PASS
echo
sudo docker exec --env-file ./.env -e CERT_PASS="$CERT_PASS" -it documenso openssl req -x509 -nodes -days 365 -newkey rsa:2048     -keyout /tmp/private.key     -out /tmp/certificate.crt     -subj '/C=US/ST=Colorado/L=Denver/O=SignatureGate/CN=documenso'
sudo docker exec --env-file ./.env -e CERT_PASS="$CERT_PASS" -it documenso openssl pkcs12 -export -legacy -out /opt/documenso/cert.p12     -inkey /tmp/private.key -in /tmp/certificate.crt     -passout env:CERT_PASS
sudo docker exec --env-file ./.env -it documenso rm /tmp/private.key /tmp/certificate.crt
```

Restart Documenso:

```bash
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml restart documenso
```

### 6.3 Verify
- Documenso should be reachable at `https://documenso.yourdomain.com`
- Health endpoint (from the Linode):
  - `curl http://localhost:3002/api/health`


### Documenso certificate signing

If Documenso documents get stuck in “Processing document…” after both recipients sign, see:

- `deploy/DOCUMENSO_CERT_TROUBLESHOOTING.md`

## 7 Grav

Launch Grav
```bash
sudo docker compose -f deploy/docker/docker-compose.yml --env-file ./.env up grav
```

Configure the Grav Administration interface at http://localhost:8085/admin


Enable NGINX and restart
```bash
sudo ln -s /etc/nginx/sites-available/grav.conf /etc/nginx/sites-enabled/grav.conf
sudo nginx -t # Test the configuration for syntax errors
sudo systemctl restart nginx
```
Ensure your DNS is configured correctly and obtain an SSL Certificate with certbot
```bash
sudo certbot --nginx -d www.yourdomain.com -d yourdomain.com
```

Edit deploy/grav/user/pages/01.home/default.md 

Point your web browser to https://www.yourdomain.com

## 8. ERPNext + Frappe HR

This repository now builds a **custom ERPNext image** that includes **HRMS at image build time**. That is important because installing HRMS later inside a running `frappe/erpnext` container is a known source of `ModuleNotFoundError: No module named 'hrms'` in Docker deployments. Frappe's Docker docs recommend building a custom image for additional apps, and the disposable demo setup is explicitly not meant for installing custom apps later. citeturn518640search0turn534888search1turn518640search7

### 8.1 Configure environment
Set these values in `.env`:

- `ERPNEXT_PUBLIC_URL=https://erp.yourdomain.com`
- `ERPNEXT_SITE_NAME=erp.yourdomain.com`
- `ERPNEXT_DB_ROOT_PASSWORD`
- `ERPNEXT_ADMIN_PASSWORD`
- `ERPNEXT_HRMS_BRANCH=version-16`

### 8.2 Build and start ERPNext services

```bash
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml build erpnext-backend

sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml up -d \
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
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml --profile erpnext-init up erpnext-bootstrap
```

### 8.4 NGINX

Enable the provided site config:

```bash
sudo cp deploy/nginx/erpnext.conf /etc/nginx/sites-available/erpnext.conf
sudo ln -sf /etc/nginx/sites-available/erpnext.conf /etc/nginx/sites-enabled/erpnext.conf
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d erp.yourdomain.com
```

### 8.5 If you previously tried runtime HRMS installation
If you already attempted to install HRMS into a running container and hit `ModuleNotFoundError: No module named 'hrms'`, tear down the partially initialized ERPNext app/site volumes before rebuilding so the new custom image can seed them cleanly:

```bash
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml down
sudo docker volume rm signaturegate_erpnext_apps signaturegate_erpnext_sites signaturegate_erpnext_logs 2>/dev/null || true
```

## 9. Operational notes
- Use ERPNext Companies for both Dank Mushrooms and Rooted Psyche inside one ERPNext site unless you later decide you need strict application-level separation.
- Keep SignatureGate / MushroomProcess application databases separate from ERPNext. Integration should happen through APIs, exports, or controlled ETL, not shared tables.
- ERPNext and Frappe HR are resource-hungry compared with Grav or n8n; monitor memory pressure closely after enabling payroll and background jobs.
