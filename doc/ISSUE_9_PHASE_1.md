# Issue #9 Phase 1 — LibreChat Core Deployment

This phase adds the core LibreChat interactive AI service to the RootedOps Docker
stack.

## Included

- LibreChat API pinned to `v0.8.7`
- MongoDB 8.0.20
- persistent Docker volumes
- host-NGINX reverse proxy configuration
- server-side OpenRouter integration
- deterministic LibreChat `modelSpecs`
- project-specific model/task prompts
- read-only GitHub MCP integration for the four Developer model specs
- registration/authentication scaffolding

## Intentionally deferred

LibreChat RAG/pgvector is not included in this first deployment phase.

The purpose is to validate the core LibreChat service, OpenRouter routing, reverse
proxy, persistence, authentication, and Linode resource headroom before adding any
optional search or document-retrieval workload. BookWorks document processing remains
Mac-local and is not a LibreChat/Linode dependency.

The MacBook's local Ollama/Llama remains completely independent.

## GitHub MCP development access

The four Developer model specs are explicitly assigned the `github` MCP server:

| Developer flow | Repository |
| --- | --- |
| RootedOps Developer | `RayzorDuff/RootedOps` |
| MushroomProcess Developer | `RayzorDuff/MushroomProcess` |
| SignatureGate Developer | `RayzorDuff/SignatureGate` |
| BookWorks Developer | `RayzorDuff/BookWorks` |

The server uses the hosted GitHub MCP endpoint with the `repos`, `issues`, and
`pull_requests` toolsets and explicitly requests read-only mode. The GitHub PAT is
provided at runtime through `GITHUB_MCP_TOKEN`; its repository scope must be enforced
by the GitHub token itself. The server is hidden from the general chat MCP picker so
that it is available through the Developer model specs rather than as a general-purpose
chat tool.

Do not commit the real GitHub token. After changing `GITHUB_MCP_TOKEN`, recreate or
restart the LibreChat service so the environment and MCP configuration are reloaded.

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

After DNS is configured for `ai.danks.store`:

```bash
sudo cp nginx/librechat.conf /etc/nginx/sites-available/librechat.conf
sudo ln -sf /etc/nginx/sites-available/librechat.conf /etc/nginx/sites-enabled/librechat.conf
sudo nginx -t
sudo systemctl reload nginx
```

Then obtain the certificate with Certbot:

```bash
sudo certbot --nginx -d ai.danks.store
```

## First-account security

LibreChat registration is configured off. Before first startup, set permanent
credentials in the real `.env`:

- `LIBRECHAT_CREDS_KEY`
- `LIBRECHAT_CREDS_IV`
- `LIBRECHAT_JWT_SECRET`
- `LIBRECHAT_JWT_REFRESH_SECRET`
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
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d   librechat-mongodb   librechat
```

Check:

```bash
sudo docker ps --filter name=librechat
sudo docker logs --tail 200 librechat
```

Do not expose MongoDB ports publicly. Meilisearch is not deployed in this phase.

## Completion criteria

Phase 1 is successful when:

1. LibreChat is reachable through the configured HTTPS hostname.
2. Authentication works.
3. Registration is closed after initial account creation.
4. OpenRouter is reachable using the server-side key.
5. Each configured modelSpec invokes its pinned model.
6. Conversation history persists across container restart.
7. No OpenRouter credentials are exposed to the browser.
8. Existing RootedOps services remain healthy.
9. Resource usage remains acceptable.

## Deferred services

RAG/pgvector and Meilisearch remain optional future additions. Add either only after
Phase 1 resource/stability validation and a concrete requirement has been identified.
BookWorks private document processing and any future BookWorks-local RAG should remain
on the Mac unless a later architectural decision explicitly changes that boundary.
