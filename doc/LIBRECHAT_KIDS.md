# LibreChat Kids

RootedOps runs the child-facing LibreChat instance separately from the adult/developer LibreChat instance.

## Architecture

- Public URL: `https://kids-ai.danks.store`
- Docker service: `librechat-kids`
- MongoDB: `librechat-kids-mongodb`
- Host-only port: `3081`
- Configuration: `docker/librechat-kids.yaml`
- NGINX site: `nginx/kids-ai.conf`
- Model: `Chat Buddy` using Google Gemini 3.8 Flash through OpenRouter
- No GitHub MCP, web search, file search, or other development integrations are configured.
- Child data is stored in separate Docker volumes from the adult LibreChat instance.

## First deployment

Create the DNS record for `kids-ai.danks.store` pointing to the Linode.

On the Linode:

```bash
cd ~/RootedOps
git pull --ff-only
```

Generate the four child-instance secrets:

```bash
openssl rand -hex 32
openssl rand -hex 16
openssl rand -hex 32
openssl rand -hex 32
```

Put those values into `.env` as `LIBRECHAT_KIDS_CREDS_KEY`, `LIBRECHAT_KIDS_CREDS_IV`, `LIBRECHAT_KIDS_JWT_SECRET`, and `LIBRECHAT_KIDS_JWT_REFRESH_SECRET`.

For initial account creation, temporarily set:

```dotenv
LIBRECHAT_KIDS_ALLOW_REGISTRATION=true
```

Validate and start only the new services:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml config >/dev/null
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d librechat-kids-mongodb librechat-kids
sudo docker compose --env-file ./.env -f docker/docker-compose.yml ps librechat-kids-mongodb librechat-kids
```

Install the NGINX site and certificate:

```bash
sudo cp nginx/kids-ai.conf /etc/nginx/sites-available/kids-ai.conf
sudo ln -sf /etc/nginx/sites-available/kids-ai.conf /etc/nginx/sites-enabled/kids-ai.conf
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d kids-ai.danks.store
```

Open `https://kids-ai.danks.store` and create the accounts. Use ordinary user accounts; do not make the children's accounts administrators.

After the accounts are created, immediately disable registration:

```dotenv
LIBRECHAT_KIDS_ALLOW_REGISTRATION=false
```

Then recreate only the kids service:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d --force-recreate librechat-kids
sudo docker compose --env-file ./.env -f docker/docker-compose.yml ps librechat-kids-mongodb librechat-kids
sudo docker compose --env-file ./.env -f docker/docker-compose.yml logs --tail=100 librechat-kids
```

## Ongoing deployment

After a RootedOps update:

```bash
cd ~/RootedOps
git pull --ff-only
sudo docker compose --env-file ./.env -f docker/docker-compose.yml config >/dev/null
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d librechat-kids-mongodb librechat-kids
```

Do not delete the `librechat_kids_*` Docker volumes during upgrades; they contain the children's accounts and conversations.

## Testing

Test both accounts independently:

1. Sign in as child 1 and verify Chat Buddy is the only available model.
2. Sign in as child 2 and verify the same.
3. Confirm `https://ai.danks.store` still exposes the adult/developer LibreChat configuration.
4. Confirm registration is disabled after account creation.
5. Ask the kids instance for a web search and a GitHub lookup; it should not have those tools available.