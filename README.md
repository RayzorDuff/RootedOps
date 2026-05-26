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

RootedOps can run a Minecraft: Bedrock Edition BedWars server using the official Bedrock Dedicated Server runtime through the `itzg/minecraft-bedrock-server` Docker image. This is the recommended runtime for self-contained Bedrock `.mcworld` minigame maps that rely on command blocks, behavior packs, resource packs, or built-in lobby controls.

This service does **not** use PocketMine or PocketMine `.phar` plugins. Do not install `BedwarsPM`, do not use `/bedwars`, and do not configure a PocketMine lobby/arena workflow for this mode. BedWars is provided by the downloaded Bedrock map itself.

Minecraft Bedrock is not an HTTP service. It uses UDP, normally on port `19132`, so it does not use the normal nginx `sites-enabled` HTTP reverse-proxy pattern used by NocoDB, n8n, Appsmith, Grav, Documenso, and ERPNext.

### Configure environment

Set these values in `.env`:

```env
MINECRAFT_BEDWARS_HOST=minecraft.yourdomain.com
MINECRAFT_BEDWARS_PORT=19132
MINECRAFT_BEDROCK_IMAGE_TAG=latest
MINECRAFT_BEDWARS_SERVER_NAME=Rooted BedWars
MINECRAFT_BEDWARS_LEVEL_NAME=bedwars_minigame
MINECRAFT_BEDWARS_GAMEMODE=adventure
MINECRAFT_BEDWARS_DIFFICULTY=normal
MINECRAFT_BEDWARS_MAX_PLAYERS=8
MINECRAFT_BEDWARS_ONLINE_MODE=true
MINECRAFT_BEDWARS_ALLOW_CHEATS=true
MINECRAFT_BEDWARS_ALLOW_LIST=true
MINECRAFT_BEDWARS_ALLOW_LIST_USERS=PlayerOneName,PlayerTwoName
```

`MINECRAFT_BEDWARS_LEVEL_NAME` must match the folder name of the installed world under `minecraft/bedrock/worlds/`. For example:

```text
minecraft/bedrock/worlds/bedwars_minigame/
```

### Install a Bedrock BedWars map

Create the persistent Bedrock server directories from the RootedOps repository root:

```bash
mkdir -p minecraft/bedrock/worlds
```

Download a Bedrock `.mcworld` BedWars map. A `.mcworld` file is a zip archive. Extract it into a world folder under `minecraft/bedrock/worlds/`:

```bash
mkdir -p /tmp/bedwars_minigame
unzip "/path/to/Bedwars Mini-Game.mcworld" -d /tmp/bedwars_minigame
mv /tmp/bedwars_minigame minecraft/bedrock/worlds/bedwars_minigame
```

After extraction, confirm the world folder contains `level.dat` directly inside the configured folder:

```text
minecraft/bedrock/worlds/bedwars_minigame/level.dat
```

If the map download includes separate `.mcpack` or `.mcaddon` behavior/resource packs, install those into the appropriate Bedrock server data folders and make sure the world references them. Some maps will load visually but will not function correctly if required packs are missing.

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

The `itzg/minecraft-bedrock-server` image accepts the Minecraft EULA with `EULA=TRUE`, maps server properties from environment variables, and publishes Bedrock on UDP `19132`.

### Private invite-only access

The Compose service enables the Bedrock allow list when `MINECRAFT_BEDWARS_ALLOW_LIST=true`. Add invited Bedrock/Xbox gamertags to:

```env
MINECRAFT_BEDWARS_ALLOW_LIST_USERS=PlayerOneName,PlayerTwoName
```

If an allow-listed player is rejected, check the container logs while they attempt to connect. Bedrock names and XUID-related details may appear in the logs and can be used to correct the allow list.

To grant operator/admin permissions, attach to the server console:

```bash
sudo docker attach minecraft-bedwars
```

Then run:

```text
op PlayerOneName
```

Detach without stopping the container with `Ctrl-p`, then `Ctrl-q`.

### DNS, firewall, and nginx

Point `minecraft.yourdomain.com` to the Linode with an `A` record. Open Bedrock's UDP port on the host firewall:

```bash
sudo ufw allow 19132/udp
```

nginx is not used for Minecraft in the recommended RootedOps setup. Let Docker publish UDP directly:

```yaml
ports:
  - "${MINECRAFT_BEDWARS_PORT}:19132/udp"
```

Do not copy a Minecraft config into `/etc/nginx/sites-available` or link it under `/etc/nginx/sites-enabled`. Those directories are HTTP virtual hosts, but Minecraft Bedrock is UDP traffic.

Bedrock clients connect to:

```text
Server Address: minecraft.yourdomain.com
Port: 19132
```

### Player flow

When using an official Bedrock server with a self-contained BedWars map:

```text
Player joins minecraft.yourdomain.com:19132
Player spawns in the downloaded map lobby
Players use the map's built-in buttons, NPCs, signs, or selectors
No /bedwars command is used
```

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
