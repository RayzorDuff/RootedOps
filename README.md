# RootedOps

RootedOps is the shared operations and deployment repository for the Rooted Psyche / Dank Mushrooms business software stack. It provides the host-level services, reverse proxy configs, persistence, backup tooling, and deployment notes used by business applications such as **MushroomProcess** and **SignatureGate**.

This repository is business infrastructure first. Application code and application-specific schema migrations belong in their own repositories; RootedOps supplies the common runtime they depend on.

## What this repository manages

RootedOps currently manages:

- Docker Compose orchestration for the shared service stack
- PostgreSQL and MariaDB database containers used by hosted applications and tools
- NocoDB for table-based administration and transition workflows
- n8n for cross-system automation and webhooks
- Appsmith for internal operational interfaces
- Documenso for self-hosted document signing
- Listmonk for self-hosted newsletters and mailing-list management
- ERPNext + HRMS for accounting, payroll, purchasing, sales, and HR operations
- Grav for lightweight public/static site hosting
- Stable MushroomProcess QR routing at `qr.danks.store` via NGINX → n8n
- NGINX reverse-proxy templates for HTTP services
- Backup and restore scripts, including Google Drive/rclone retention pruning
- Optional Minecraft Bedrock server hosting as a sidecar/family service

## What this repository does not manage

RootedOps intentionally does not contain:

- SignatureGate application code or release history
- MushroomProcess application code or release history
- Appsmith application exports, unless intentionally staged here for deployment support
- Application-specific PostgreSQL schema migrations that belong in the application repositories
- Airtable/NocoDB/Appsmith parity testing artifacts, except where they are needed as infrastructure notes

## Service overview

### SignatureGate database

`signaturegate-postgres` is a dedicated PostgreSQL service for the SignatureGate application stack. SignatureGate itself remains a separate application repository, while RootedOps provides the database container, credentials, backups, and network location it can run against.

SignatureGate-related automation also appears in the RootedOps environment because n8n workflows may need access to shared infrastructure, Documenso, and operational reporting destinations.

### MushroomProcess bridge database

`mushroomprocess-bridge-postgres` is the RootedOps-hosted PostgreSQL bridge/database service for MushroomProcess-related integration work. MushroomProcess application code, Appsmith exports, schema files, and release history live outside this repository, but this stack gives the project a local Postgres endpoint that can be used by NocoDB, Appsmith, n8n, and transition workflows.

This separation keeps MushroomProcess development and parity testing in the MushroomProcess repository while allowing RootedOps to operate the shared database and automation layer.

### NocoDB

NocoDB runs with its own metadata PostgreSQL database and is configured to allow connections to local external databases. In this stack it acts as a low-code/admin data interface for operational databases such as SignatureGate and MushroomProcess bridge data.

NocoDB persistent data is stored in the `nocodb_data` Docker volume, while metadata is stored in `nocodb_meta_pgdata`.

### n8n automation

n8n is the workflow automation layer. The `.env.example` shows the integration surface currently expected by RootedOps, including:

- Documenso API access
- NocoDB API access
- temporary Airtable access for MushroomProcess migration/transition workflows
- Givebutter webhook signature validation
- ERPNext API access
- Ecwid webhook/API integration
- Clover API integration
- scheduled/reporting email destinations

The repository currently includes an n8n workflow export for bank CSV upload into ERPNext. Additional n8n workflows can be imported into the running n8n instance and should be documented when they become part of the operational baseline.

### Listmonk

Listmonk is included as the self-hosted mailing-list and newsletter manager. It runs as `listmonk` with its own `listmonk-postgres` database and a bind-mounted media upload directory at `listmonk/uploads`. RootedOps operates Listmonk and backs up its database/uploads; SignatureGate should remain the source of truth for identity, consent, and member status, with n8n or future SignatureGate integration syncing subscribers into Listmonk.

After first login, configure Listmonk Admin -> Settings -> Media to use `/listmonk/uploads`, then create an API token and place it in `.env` for n8n/SignatureGate sync workflows.

### Appsmith

Appsmith is included as the internal UI/runtime layer for operational tools. The container persists its state in `appsmith_stacks`. RootedOps operates the Appsmith service, while complex application exports and test-pass artifacts should remain with the application project that owns them.

### Documenso

Documenso provides self-hosted document signing. RootedOps includes:

- a custom Documenso Dockerfile
- a dedicated Documenso PostgreSQL database
- NGINX proxy configuration
- signing certificate mount support at `documenso/certs/cert.p12`
- environment variables for SMTP, signing, encryption, and public URL configuration

Operational setup details are in `LINODE_SETUP.md`.

### ERPNext + HRMS

ERPNext is the business accounting and HR platform in this stack. RootedOps builds a custom ERPNext image that includes HRMS, Employee Self Service, and the RootedOps payroll app support files.

The `erpnext/` directory contains the current living implementation notes, data templates, and scripts for:

- multi-company ERPNext setup
- accounting master data
- suppliers, projects, cost centers, departments, employees, designations, and asset categories
- HRMS installation and site initialization
- attendance-driven hourly payroll support
- payroll entry UI support
- salary-slip hours support
- bank and payroll account setup/audit helpers

For ERPNext continuation work, start with:

- `erpnext/README.md`
- `erpnext/CHATGPT_HANDOFF.md`
- `erpnext/CHATGPT_HANDOFF.json`
- `erpnext/README_SCRIPTS.md`

### Grav

Grav is included for lightweight website hosting. The repository includes a minimal Grav content/theme scaffold and an NGINX config for public HTTP/TLS routing.

### Minecraft Bedrock

Minecraft Bedrock hosting is supported as an optional sidecar service, not a core business component. It uses the official Bedrock Dedicated Server runtime and downloaded Bedrock `.mcworld` maps.

Detailed Minecraft setup has been moved out of this README to keep RootedOps focused on business operations:

- `README_MINECRAFT.md`

## Quick start

From the repository root:

```bash
cp .env.example .env
nano .env
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d
sudo docker ps
```

Local service ports:

| Service | Local URL / port |
| --- | --- |
| NocoDB | `http://localhost:8080` |
| n8n | `http://localhost:5678` |
| Appsmith | `http://localhost:8081` |
| ERPNext | `http://localhost:8086` |
| Grav | `http://localhost:8085` |
| Documenso | `http://localhost:3002` |
| Listmonk | `http://localhost:9000` |
| Minecraft Bedrock | UDP `19132` |

## Repository layout

```text
docker/              Compose stack and custom Dockerfiles
listmonk/uploads/    Bind-mounted Listmonk media upload directory
nginx/               HTTP reverse-proxy site configs
                      Includes `qr.conf` for the stable MushroomProcess QR resolver
backup/              Backup, restore, and rclone service helpers
erpnext/             ERPNext/HRMS templates, scripts, and handoff notes
n8n/                 Workflow exports that are part of this ops baseline
grav/                Grav bind-mount target
grav.mysite/         Starter Grav site/theme/content scaffold
doc/                 RootedOps changelog and repository notes
README_MINECRAFT.md  Optional Minecraft Bedrock sidecar service notes
LINODE_SETUP.md      Practical Linode deployment guide
linode_bootstrap.sh  Convenience bootstrap script for a new Ubuntu host
```

## Deployment notes

The main deployment guide is:

- `LINODE_SETUP.md`

That guide covers host provisioning, firewall, Docker installation, NGINX, Certbot, persistent data, Documenso setup, Grav setup, ERPNext initialization, Google Drive/rclone backup mount setup, backup execution, restore procedure, and maintenance notes.

## Backups

RootedOps includes backup and restore scripts under `backup/`.

The backup script handles:

- PostgreSQL logical dumps for SignatureGate, MushroomProcess bridge, Listmonk, NocoDB metadata, and Documenso
- MariaDB dump for ERPNext
- Docker volume archives for NocoDB, n8n, Appsmith, ERPNext sites/apps/logs, and other persistent service state
- bind-mounted Listmonk media uploads
- bind-mounted operational files such as `.env`, nginx configs, Grav files, Documenso certificate material, and optional Minecraft Bedrock data
- upload/copy to an rclone remote such as Google Drive
- retention pruning for old remote backup directories

Minecraft Bedrock data is included as `bind_mounts/minecraft-bedrock.tgz` when `MINECRAFT_BEDROCK_DATA_PATH` is configured. The script stops `minecraft-bedwars` during that archive by default to avoid copying an active Bedrock LevelDB world.

## Relationship to MushroomProcess and SignatureGate

Recommended use:

- Keep RootedOps as the shared infrastructure and deployment repository.
- Keep MushroomProcess schema, Appsmith exports, release notes, issue tracking, and parity testing artifacts in the MushroomProcess repository.
- Keep SignatureGate app code, release notes, and application schema in the SignatureGate repository.
- Use RootedOps for shared databases, n8n automation, reverse proxy, backups, and deployment documentation.

This division keeps the operational stack stable while allowing MushroomProcess and SignatureGate to evolve independently.

## License

This repository is licensed under **GNU GPL v3.0**. See `LICENSE`.

Rationale: MushroomProcess and SignatureGate are GPL; choosing GPLv3 here keeps license compatibility for shared code or common operational modules between projects.

QR Product routing also passes `MP_APP_PRODUCTS_URL` and `MP_REGULATED_BUSINESS_URL` into n8n; see `LINODE_SETUP.md`.
