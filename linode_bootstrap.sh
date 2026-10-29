#!/usr/bin/env bash
set -Eeuo pipefail
# Fresh Ubuntu 24.04 test host preparation. Starting/restoring is explicit.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="${1:-$REPO_ROOT/.test-deployment}"
if [[ ${EUID} -ne 0 ]]; then exec sudo bash "$0" "$@"; fi
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || {
  echo 'Supported bootstrap target: Ubuntu 24.04 LTS' >&2; exit 1;
}
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg ufw fail2ban git openssl python3 python3-yaml \
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
python3 "$REPO_ROOT/scripts/host_recovery.py" prepare "$DEPLOYMENT_DIR"
if [[ -n "${SUDO_UID:-}" && "$SUDO_UID" != 0 ]]; then
  chown -R "$SUDO_UID:${SUDO_GID}" "$DEPLOYMENT_DIR"
  chown -h "$SUDO_UID:${SUDO_GID}" "$REPO_ROOT/.env"
fi
printf '%s\n' 'Host packages and private full-stack test configuration are ready.' \
  "Next: python3 $REPO_ROOT/scripts/host_recovery.py validate $DEPLOYMENT_DIR" \
  "Then: sudo python3 $REPO_ROOT/scripts/host_recovery.py start $DEPLOYMENT_DIR" \
  'See doc/fresh-host-recovery.md for external keys, setup accounts, DNS and full restore.'
