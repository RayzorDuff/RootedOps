# RootedOps
Docker and database configuration, backups and infrastructure backend for MushroomProcess and SignatureGate

## Quick start (Docker Compose)

1. Copy environment file:
   ```bash
   cp .env.example .env
   ```
2. Start services:
   ```bash
   docker compose -f deploy/docker/docker-compose.yml up -d
   ```
3. Open:
   - NocoDB: http://localhost:8080
   - n8n: http://localhost:5678
   - Appsmith: http://localhost:8081
   - ERPNext: http://localhost:8086

## License

This repository is licensed under **GNU GPL v3.0** (see `LICENSE`).

Rationale: MushroomProcess and SignatureGate are GPL; choosing GPLv3 here keeps license compatibility to allow for shared code or common modules between projects.

## ERPNext / Frappe HR

The deployment stack now includes an optional ERPNext + Frappe HR installation path for bookkeeping, expense tracking, payroll, and contractor / employee administration.
The ERPNext image is built locally with HRMS included so payroll and HR features survive container restarts and remain available across backend, worker, scheduler, websocket, and frontend services.

- Long-running ERPNext services live in `docker/docker-compose.yml`.
- One-time site creation and HRMS installation are handled by `ocker/erpnext-bootstrap.sh`.
- Reverse proxying is provided by `nginx/erpnext.conf`.
- Host-level setup is documented in `LINODE_SETUP.md`.

Recommended use: keep both businesses as separate ERPNext Companies within one ERPNext site, while leaving SignatureGate and MushroomProcess on their own application databases.
