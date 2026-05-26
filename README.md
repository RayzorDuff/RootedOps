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



## Minecraft Bedrock BedWars service

RootedOps can run a Minecraft: Bedrock Edition BedWars server using PocketMine-MP plus a BedWars plugin such as `BedwarsPM` from Poggit.

Minecraft Bedrock is not an HTTP service. It uses UDP, normally on port `19132`, so it does not use the normal `nginx/sites-enabled` HTTP reverse-proxy pattern used by NocoDB, n8n, Appsmith, Grav, Documenso, and ERPNext.

### Configure environment

Set these values in `.env`:

```env
MINECRAFT_BEDWARS_HOST=minecraft.yourdomain.com
MINECRAFT_BEDWARS_PORT=19132
MINECRAFT_BEDWARS_POCKETMINE_TAG=5.43.1
```

For a manually downloaded BedWars `.phar`, leave the Poggit auto-download variable blank:

```env
MINECRAFT_BEDWARS_POCKETMINE_PLUGINS=
```

Only set `MINECRAFT_BEDWARS_POCKETMINE_PLUGINS` when using a confirmed Poggit plugin slug and version. The format is space-separated `PluginName[:version]` values, for example:

```env
MINECRAFT_BEDWARS_POCKETMINE_PLUGINS=PluginOne:1.2.3 PluginTwo
```

### Install the BedWars plugin manually

Create the bind-mounted PocketMine directories from the RootedOps repository root:

```bash
mkdir -p minecraft/bedwars/data minecraft/bedwars/plugins
```

Download the BedWars plugin `.phar` and place it in:

```text
minecraft/bedwars/plugins/
```

For example, if using the Poggit `BedwarsPM` download, the file should live under:

```text
minecraft/bedwars/plugins/BedwarsPM.phar
```

The PocketMine container runs as UID/GID `1000:1000`. If the directories were created by `root`, fix ownership before startup:

```bash
sudo chown -R 1000:1000 minecraft/bedwars
```

### Start and inspect the server

From the RootedOps repository root:

```bash
sudo docker compose --env-file .env -f docker/docker-compose.yml up -d minecraft-bedwars
sudo docker logs -f minecraft-bedwars
```

If launching the full stack instead of only Minecraft:

```bash
sudo docker compose --env-file .env -f docker/docker-compose.yml up -d
```

### DNS, firewall, and nginx

Point `minecraft.yourdomain.com` to the Linode with an `A` record. Open Bedrock's UDP port on the host firewall:

```bash
sudo ufw allow 19132/udp
```

Do not copy `nginx/minecraft-bedwars.stream.conf` into `/etc/nginx/sites-available` or link it under `/etc/nginx/sites-enabled`. Those directories are normally included inside nginx's `http {}` context, and `listen ... udp` is only valid in nginx's top-level `stream {}` context.

The recommended RootedOps setup is direct Docker UDP publishing:

```yaml
ports:
  - "${MINECRAFT_BEDWARS_PORT}:19132/udp"
```

With direct Docker publishing, nginx is not involved for Minecraft. Bedrock clients connect to:

```text
Server Address: minecraft.yourdomain.com
Port: 19132
```

Optional nginx stream proxying is only needed if nginx must own the public UDP listener. In that case, configure a top-level nginx `stream {}` include and use a separate Docker backend port, such as public `19132/udp` to nginx and localhost backend `19133/udp` to the container. Do not have nginx and Docker both bind public `19132/udp`.

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
