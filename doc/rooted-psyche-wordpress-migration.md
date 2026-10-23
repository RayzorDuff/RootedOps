# Rooted Psyche: Grav to WordPress migration

This is a staged migration. The current Grav site stays online until WordPress is verified. The new WordPress Compose file is intentionally separate from the existing stack so normal RootedOps `docker compose` operations do not start it.

## 1. Preflight on the Linode

```bash
cd ~/RootedOps
git pull --ff-only origin main
free -h
df -h
sudo docker stats --no-stream
sudo docker compose --env-file ./.env -f docker/docker-compose.yml ps grav
sudo nginx -T | grep -A25 -B3 'proxy_pass http://localhost:8085'
```

Confirm memory, disk, the active domain and SSL configuration, and that a recent backup of `grav/` and the Nginx site configuration exists. Do not paste credentials or the full `.env` into an issue.

## 2. Start isolated WordPress

Generate **two different** strong passwords and add these lines to the local `.env` (never commit secrets):

```dotenv
ROOTEDPSYCHE_WP_DB_PASSWORD=<generated-unique-password>
ROOTEDPSYCHE_WP_DB_ROOT_PASSWORD=<different-generated-unique-password>
ROOTEDPSYCHE_WP_TEST_PORT=8096
```

Then:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.wordpress.yml config --quiet
sudo docker compose --env-file ./.env -f docker/docker-compose.wordpress.yml up -d
sudo docker compose --env-file ./.env -f docker/docker-compose.wordpress.yml ps
curl -I http://127.0.0.1:8096/
```

WordPress listens only on loopback. Use an SSH tunnel from your Mac to complete the installer without exposing the unfinished site:

```bash
ssh -L 8096:127.0.0.1:8096 <linode-ssh-host>
```

Then visit `http://localhost:8096`. Do not use the public hostname as the WordPress site URL until cutover. Create an administrator account with a unique password and use the site's intended public title.

## 3. Migrate homepage

Source: `grav.mysite/user/pages/01.home/default.md` and its `qr.png`. Reproduce the existing **Mission**, **Vision**, and **Core Values** sections, upload the QR image to WordPress Media, and preserve the working Givebutter integration. The source contains a Givebutter widget loader and `<givebutter-widget id="gJeP4L"></givebutter-widget>`; confirm the correct current embed configuration from Givebutter before placing it in a WordPress Custom HTML block. WordPress may filter script tags depending on permissions and settings, so test the rendered public page. Do not enter test donations without appropriate safeguards.

Keep the first release minimal: a homepage, basic theme, working donation action, and existing privacy/contact details if present in the deployed site. Do not add WooCommerce or an elaborate page builder.

## 4. Validate and cut over

- Confirm WordPress health, memory/disk use, mobile layout, uploads, and homepage text.
- Back up the WordPress database and uploads; verify restoration procedure. Back up existing Grav runtime content and Nginx configuration.
- Inspect **deployed** Nginx config, not only `nginx/grav.conf` (which contains placeholder domains).
- At cutover, stop Grav and publish WordPress through the same established public host and TLS endpoint. One option is changing the active proxy upstream from port 8085 to WordPress's local port 8096, followed by `sudo nginx -t && sudo systemctl reload nginx`. This is a targeted Nginx change, not a redesign.
- Configure WordPress canonical home/site URLs for HTTPS at the real hostname, avoiding redirects to localhost. Validate frontend, admin login, permalinks, media, and Givebutter.
- Keep Grav data and configuration archived until the rollback window is closed. Rollback means restoring the previous proxy upstream and restarting Grav; document any new content written after cutover.

## 5. Follow-on

Build the sanctuary campaign landing page after WordPress cutover. BookWorks remains the editorial source; WordPress publishes the public presentation; Givebutter handles donations.

**Do not** shut down Grav or switch Nginx merely because the new containers start. The live cutover requires the validation steps above.
