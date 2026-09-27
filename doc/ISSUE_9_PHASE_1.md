# Issue #9 Phase 1 — LibreChat Core Deployment

This phase adds the core LibreChat interactive AI service to the RootedOps Docker
stack.

## Included

- LibreChat API pinned to `v0.8.7`
- MongoDB 8.0.20
- Meilisearch v1.35.1
- persistent Docker volumes
- host-NGINX reverse proxy configuration
- server-side OpenRouter integration
- deterministic LibreChat `modelSpecs`
- project-specific model/task prompts
- registration/authentication scaffolding

## Intentionally deferred

LibreChat RAG/pgvector is not included in this first deployment phase.

The purpose is to validate the core LibreChat service, OpenRouter routing, reverse
proxy, persistence, authentication, and Linode resource headroom before adding the
additional RAG API and vector database workload.

The MacBook's local Ollama/Llama remains completely independent.

## Current model assignments

| Workspace | Model |
| --- | --- |
| RootedOps Developer | `anthropic/claude-sonnet-5` |
| MushroomProcess Developer | `anthropic/claude-sonnet-5` |
| SignatureGate Developer | `anthropic/claude-sonnet-5` |
| BookWorks Developer | `anthropic/claude-sonnet-5` |
| BookWorks Legal Research | `google/gemini-3.1-pro-preview` |
| BookWorks Case History | `google/gemini-3.8-flash` |
| BookWorks County & Real Estate | `google/gemini-3.8-flash` |
| BookWorks Document Analysis | `google/gemini-3.8-flash` |
| BookWorks Writer | `meta-llama/llama-3.3-70b-instruct` |
| Personal Writer | `meta-llama/llama-3.3-70b-instruct` |
| Conversation Analysis | `anthropic/claude-sonnet-5` |
| General Research | `google/gemini-3.8-flash` |
| Technical & Architecture Research | `anthropic/claude-sonnet-5` |
| General Reasoning | `meta-llama/llama-3.3-70b-instruct` |
| DeepSeek Coding | `deepseek/deepseek-v4-flash-0731` |

Exact model IDs and pricing should be re-verified before deployment because the
OpenRouter catalog changes.

## Deployment preflight

Before starting the new services on the Linode:

```bash
free -h
nproc
df -h
sudo docker stats --no-stream
sudo docker system df
```

Record the results. Do not proceed if the existing RootedOps workload has
insufficient RAM/disk headroom.

## NGINX activation

After DNS is configured:

```bash
sudo ln -sf /etc/nginx/sites-available/librechat.conf /etc/nginx/sites-enabled/librechat.conf
sudo nginx -t
sudo systemctl reload nginx
```

Then obtain the certificate with Certbot using the actual LibreChat hostname.

## First-account security

LibreChat registration is configured off. Before first startup, set permanent
credentials in the real `.env`:

- `LIBRECHAT_CREDS_KEY`
- `LIBRECHAT_CREDS_IV`
- `LIBRECHAT_JWT_SECRET`
- `LIBRECHAT_JWT_REFRESH_SECRET`
- `LIBRECHAT_MEILI_MASTER_KEY`
- `OPENROUTER_KEY`

Generate them with cryptographically secure random values. Do not commit the real
`.env`.

Create the initial user before disabling registration if the chosen LibreChat
version requires the initial registration flow. After the account exists, retain
`LIBRECHAT_ALLOW_REGISTRATION=false`.

## Compose validation

Run:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml config
```

before starting the new services.

Then start only the phase-1 services:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d   librechat-mongodb   librechat-meilisearch   librechat
```

Check:

```bash
sudo docker ps --filter name=librechat
sudo docker logs --tail 200 librechat
```

Do not expose MongoDB or Meilisearch ports publicly.

## Completion criteria

Phase 1 is successful when:

1. LibreChat is reachable through the configured HTTPS hostname.
2. Authentication works.
3. Registration is closed after initial account creation.
4. OpenRouter is reachable using the server-side key.
5. Each configured modelSpec invokes its pinned model.
6. Conversation history persists across container restart.
7. Meilisearch-backed conversation search works.
8. No OpenRouter credentials are exposed to the browser.
9. Existing RootedOps services remain healthy.
10. Resource usage remains acceptable.

## Next phase

Phase 2 should add LibreChat RAG/pgvector after the phase-1 resource and stability
validation. The RAG implementation should use the current official image/configuration
available at that time and should be included in RootedOps backup/restore procedures.
