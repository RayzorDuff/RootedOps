#!/usr/bin/env bash
set -euo pipefail

# SignatureGate bootstrap (Ubuntu). Review before running.
# This script is a convenience starter — adapt for your environment.

sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg ufw fail2ban git

# Firewall
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "Base packages installed. Next: install Docker per official docs:"
echo "https://docs.docker.com/engine/install/ubuntu/"
