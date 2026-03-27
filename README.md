# RootedOps
Infrastructure, reverse proxy, container orchestration, backups, and shared service hosting for Rooted Psyche, Dank Mushrooms, MushroomProcess, and SignatureGate.

This repository is the standalone operations and deployment project that was split out from SignatureGate. It is responsible for host setup and shared service infrastructure. Application repositories such as SignatureGate and MushroomProcess should keep their own application code and database schema, while this repository provides the host-level stack they can run against.

## What this repository contains

- Docker Compose stack for shared services and databases
- NGINX reverse proxy configurations
- Grav website hosting
- Documenso hosting
- ERPNext + HRMS hosting
- Backup and restore scripts
- Linode host setup guidance

## What this repository does not contain

- SignatureGate application code or release history
- MushroomProcess application code or release history
- Application-specific deployment architecture that belongs inside those repos

## Quick start (Docker Compose)

1. Copy environment file:
   ```bash
   cp .env.example .env
   ```
2. Review and edit `.env` for your hostnames, passwords, API tokens, and backup settings.
3. Start services:
   ```bash
   docker compose --env-file ./.env -f docker/docker-compose.yml up -d
   ```
4. Open local service ports as needed:
   - NocoDB: http://localhost:8080
   - n8n: http://localhost:5678
   - Appsmith: http://localhost:8081
   - ERPNext: http://localhost:8086
   - Grav: http://localhost:8085
   - Documenso: http://localhost:3002

## Repository layout

- `docker/` - Compose stack and custom Dockerfiles
- `nginx/` - Example reverse proxy site configs
- `grav/` - Grav site files and content
- `backup/` - Backup, restore, and rclone service helpers
- `LINODE_SETUP.md` - Practical host bootstrap and deployment notes
- `linode_bootstrap.sh` - Convenience bootstrap script for a new Ubuntu host

## Relationship to SignatureGate and MushroomProcess

Recommended use: keep Rooted Psyche and Dank Mushrooms as separate ERPNext Companies within one ERPNext site, while leaving SignatureGate and MushroomProcess on their own application databases. Those application repositories should contain their own schema and app-layer assets; this repository supplies the shared operational environment.

## License

This repository is licensed under **GNU GPL v3.0** (see `LICENSE`).

Rationale: MushroomProcess and SignatureGate are GPL; choosing GPLv3 here keeps license compatibility to allow for shared code or common modules between projects.


## ERPNext operational note
The `erpnext/` directory now contains a living implementation and documentation set for:
- attendance-driven hourly payroll
- batched payroll processing
- Payroll Entry UI integration
- multi-company payroll support
- hybrid overnight compensation support

When continuing ERPNext work in a new session, start with:
- `erpnext/README.md`
- `erpnext/CHATGPT_HANDOFF.md`
- `erpnext/CHATGPT_HANDOFF.json`
- `erpnext/scripts/README_SCRIPTS.md`
