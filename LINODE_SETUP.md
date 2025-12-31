# Linode setup (Linux)

This is intentionally high-level and points you to upstream docs where appropriate.

## 0. Provision
- Ubuntu 22.04/24.04 LTS
- Enable backups, add an SSH key, disable password SSH.

## 1. Baseline hardening
- Create non-root user, add to sudo
```bash
useradd -m singaturegate
passwd signaturegate
usermod -aG sudo signaturegate
```
- Configure UFW: allow 22, 80, 443, 8080
```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 8080/tcp && sudo ufw --force enable
```
- Install fail2ban and dotenv
```bash
sudo apt-get install -y ca-certificates curl gnupg ufw fail2ban git python3 python3-dotenv-cli
```
- Keep system updated

## 2. Install Docker
Follow Docker’s official instructions for Ubuntu:
https://docs.docker.com/engine/install/ubuntu/

## 3. Deploy SignatureGate stack
```bash
su signaturegate
ssh-keygen -t ed25519 -C "your@email.com"
cat ~/.ssh/id_ed25519.pub (For access to SignatureGate git)
git clone git@github.com/RayzorDuff/SignatureGate.git signaturegate
cd signaturegate
cp .env.example .env
# edit secrets in .env
sudo docker compose --env-file ./.env -f deploy/docker/docker-compose.yml up -d
sudo docker ps
sudo docker logs nocodb
```

## 4. Add TLS + reverse proxy (recommended)
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
sudo certbot --nginx -d yourdomain.com
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
docker-compose up -d
```

Use Caddy or Traefik (not included yet).
- Terminate TLS for NocoDB, Appsmith
- Put n8n and Appsmith behind auth / VPN if you want them internal-only

## 5. Backups
- pg_dump nightly for each Postgres volume
- snapshot volumes
- store agreement evidence files in object storage and back it up

