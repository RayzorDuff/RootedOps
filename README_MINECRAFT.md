# Minecraft Bedrock sidecar service

RootedOps can optionally run a private Minecraft: Bedrock Edition server for BedWars maps. This is not a core business component of RootedOps; it is a sidecar service that shares the same Docker/backup/deployment framework.

The current configuration uses the official Bedrock Dedicated Server runtime through the `itzg/minecraft-bedrock-server` Docker image. This is the preferred runtime for downloaded Bedrock `.mcworld` minigame maps that rely on command blocks, behavior packs, resource packs, built-in NPCs, or map lobby controls.

## Runtime choice

Use the official Bedrock Dedicated Server for self-contained Bedrock maps:

```text
Official Bedrock Dedicated Server
  - runs Bedrock .mcworld maps and built-in map logic
  - supports command-block/map behavior better than PocketMine
  - does not use PocketMine .phar plugins
  - does not use /bedwars
```

Do not install BedwarsPM or other PocketMine `.phar` plugins with this service. BedWars gameplay comes from the downloaded Bedrock map itself.

PocketMine is a different server runtime:

```text
PocketMine
  - runs PocketMine plugins such as BedwarsPM
  - uses .phar plugins
  - can support plugin-managed arenas
  - does not reliably run command-block Bedrock minigame maps
```

The RootedOps Minecraft service is currently the first option: official Bedrock Dedicated Server.

## Environment variables

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

`MINECRAFT_BEDWARS_LEVEL_NAME` must match the world folder under:

```text
minecraft/bedrock/worlds/
```

For example:

```text
minecraft/bedrock/worlds/bedwars_mini/
```

requires:

```env
MINECRAFT_BEDWARS_LEVEL_NAME=bedwars_mini
```

Do not manually edit `minecraft/bedrock/server.properties` for settings that are controlled by Docker environment variables. The container rewrites supported server properties at startup.

## Install a Bedrock `.mcworld` map

From the RootedOps repository root:

```bash
mkdir -p minecraft/bedrock/worlds
mkdir -p /tmp/bedwars_map
unzip "/path/to/Bedwars Mini-Game.mcworld" -d /tmp/bedwars_map
mv /tmp/bedwars_map minecraft/bedrock/worlds/bedwars_mini
```

Confirm that `level.dat` is directly inside the configured world folder:

```text
minecraft/bedrock/worlds/bedwars_mini/level.dat
```

If the world is nested one level too deep, the server may start a blank or wrong world. The correct layout is:

```text
minecraft/bedrock/worlds/<world_folder>/level.dat
minecraft/bedrock/worlds/<world_folder>/db/
```

Many Bedrock maps include behavior/resource pack references inside the world folder:

```text
world_behavior_packs.json
world_resource_packs.json
behavior_packs/
resource_packs/
```

If the download also includes separate `.mcpack` or `.mcaddon` files, install the required packs in the Bedrock server data folder and confirm the world references them. A map may load visually but fail to show controls or custom gameplay if required packs are missing.

## Start the server

Start only Minecraft:

```bash
sudo docker compose --env-file .env -f docker/docker-compose.yml up -d minecraft-bedwars
sudo docker logs -f minecraft-bedwars
```

Or start the full stack:

```bash
sudo docker compose --env-file .env -f docker/docker-compose.yml up -d
```

The logs should show the configured level name, for example:

```text
Setting level-name to bedwars_mini in server.properties
Level Name: bedwars_mini
Opening level 'worlds/bedwars_mini/db'
```

## Client connection

Bedrock clients connect with:

```text
Server Address: minecraft.yourdomain.com
Port: 19132
```

For a host named `elwell.edanks.com`, use:

```text
Server Address: elwell.edanks.com
Port: 19132
```

Do not use `http://`, `https://`, or an nginx path. Minecraft Bedrock uses UDP.

## DNS, firewall, and nginx

Create a DNS `A` record:

```text
minecraft.yourdomain.com -> your Linode IPv4 address
```

Open the Bedrock UDP port:

```bash
sudo ufw allow 19132/udp
sudo ufw status
```

nginx is not used for Minecraft in the recommended RootedOps setup. Let Docker publish UDP directly:

```yaml
ports:
  - "${MINECRAFT_BEDWARS_PORT}:19132/udp"
```

Do not install a Minecraft config under `/etc/nginx/sites-available` or `/etc/nginx/sites-enabled`; those are HTTP virtual host directories. If a previous stream config was installed there and nginx reports `invalid parameter "udp"`, remove it:

```bash
sudo rm -f /etc/nginx/sites-enabled/minecraft-bedwars.stream.conf
sudo rm -f /etc/nginx/sites-available/minecraft-bedwars.stream.conf
sudo nginx -t
sudo systemctl reload nginx
```

## Private invite-only access

Enable the Bedrock allow list:

```env
MINECRAFT_BEDWARS_ALLOW_LIST=true
MINECRAFT_BEDWARS_ALLOW_LIST_USERS=PlayerOneName,PlayerTwoName
```

Use Bedrock/Xbox gamertags. If a player is rejected, watch logs during their connection attempt:

```bash
sudo docker logs -f minecraft-bedwars
```

Then correct the allow-list entry from the name/XUID information shown by the server.

## Operator access

Attach to the server console:

```bash
sudo docker attach minecraft-bedwars
```

Run:

```text
op PlayerOneName
```

Detach without stopping the container by pressing:

```text
Ctrl-p Ctrl-q
```

For temporary debugging, an operator can use in-game commands such as:

```text
/gamemode creative
/gamemode adventure
```

## Player flow

For self-contained Bedrock BedWars maps:

```text
Players join minecraft.yourdomain.com:19132
Players spawn in the downloaded map lobby
Players use the map's built-in buttons, signs, NPCs, selectors, or start controls
No /bedwars command is used
```

If the world loads but there are no controls, check:

1. `MINECRAFT_BEDWARS_LEVEL_NAME` matches the actual world folder name.
2. `level.dat` is directly inside `minecraft/bedrock/worlds/<world_folder>/`.
3. Required behavior/resource packs are present.
4. Player spawned in the intended lobby; temporarily use OP/creative to inspect.
5. The map is compatible with the currently running Bedrock server version.

## Multiple maps

The official Bedrock Dedicated Server runs one active world per server instance. Other folders under `minecraft/bedrock/worlds/` are not live-selectable by players through a built-in `/world` command.

To change maps, update:

```env
MINECRAFT_BEDWARS_LEVEL_NAME=other_world_folder
```

Then recreate/restart the server:

```bash
sudo docker compose --env-file .env -f docker/docker-compose.yml down
sudo docker compose --env-file .env -f docker/docker-compose.yml up -d minecraft-bedwars
```

If multiple maps should be online at the same time, run multiple Bedrock server containers on different UDP ports and separate `/data` mounts.

## Backups

The RootedOps backup script can archive the Minecraft Bedrock data directory as:

```text
bind_mounts/minecraft-bedrock.tgz
```

Relevant `.env` values:

```env
MINECRAFT_BEDROCK_DATA_PATH=./minecraft/bedrock
MINECRAFT_BACKUP_STOP_CONTAINER=true
```

The default behavior stops `minecraft-bedwars` while archiving the Bedrock data directory so the active LevelDB world is copied consistently, then starts the service again afterward.
