# Linode setup (Linux)

This is intentionally high-level and points you to upstream docs where appropriate.

## 0. Provision
- Ubuntu 22.04/24.04 LTS
- Enable backups, add an SSH key, disable password SSH.

## 1. Baseline hardening
- Create non-root user, add to sudo
- Configure UFW: allow 22, 80, 443
- Install fail2ban
- Keep system updated

## 2. Install Docker
Follow Docker’s official instructions for Ubuntu:
https://docs.docker.com/engine/install/ubuntu/

## 3. Deploy SignatureGate stack
```bash
git clone <your-fork-url> signaturegate
cd signaturegate
cp .env.example .env
# edit secrets in .env
docker compose -f deploy/docker/docker-compose.yml up -d
```

## 4. Add TLS + reverse proxy (recommended)
Use Caddy or Traefik (not included yet).
- Terminate TLS for NocoDB, n8n, Appsmith
- Put n8n and Appsmith behind auth / VPN if you want them internal-only

## 5. Backups
- pg_dump nightly for each Postgres volume
- snapshot volumes
- store agreement evidence files in object storage and back it up

