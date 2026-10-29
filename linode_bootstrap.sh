#!/usr/bin/env bash
set -Eeuo pipefail
# Fresh Ubuntu 24.04 test hosts only. Does not start apps or restore data.
if [[ ${EUID} -ne 0 ]]; then exec sudo bash "$0" "$@"; fi
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || {
  echo 'Supported bootstrap target: Ubuntu 24.04 LTS' >&2; exit 1;
}
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg ufw fail2ban git python3 python3-yaml \
  python3-cryptography nginx certbot python3-certbot-nginx rclone postgresql-client
# Use Ubuntu's maintained packages on a fresh host. Preserve existing Docker CE.
if ! command -v docker >/dev/null; then apt-get install -y docker.io docker-compose-v2; fi
docker compose version >/dev/null || { echo 'Install the Compose v2 plugin for the existing Docker installation' >&2; exit 1; }
systemctl enable --now docker nginx fail2ban
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
# Docker-published ports bypass UFW: the test renderer binds all ports to loopback.
printf '%s\n' 'Bootstrap complete. Follow doc/test-environment-restore.md.' \
  'No app ports, virtual hosts, certificates, or production credentials were installed.'
