# RootedOps 1.5.5

## Issue #9 Phase 1 — Minecraft operational control

- Placed the Minecraft Bedrock BedWars service behind the Docker Compose `minecraft` profile.
- Added `COMPOSE_PROFILES` to `.env.example` so Minecraft can be enabled or disabled without changing the Compose file.
- Leaving `COMPOSE_PROFILES` empty keeps Minecraft disabled; setting `COMPOSE_PROFILES=minecraft` enables it.

This is an incremental Issue #9 development phase. No Git tag is created for this patch release.
