# Rooted Psyche scheduling (RootedOps issue #17)

Services: Rallly at https://poll.rootedpsyche.org and Tymeslot at https://schedule.rootedpsyche.org.

## SMTP
Reuse the Listmonk-tested Gmail app-password pattern: smtp.gmail.com, port 587, STARTTLS, SMTP authentication with the full Gmail login. The sender address must be authorized by that Gmail account. Do not commit passwords or application encryption keys. Gmail quotas and spam filtering may affect notifications.

## Tymeslot
The Compose project is intentionally separate to avoid disrupting the main stack.
In the RootedOps root .env add:
```dotenv
TYMESLOT_IMAGE_TAG=<pin-a-verified-upstream-release>
TYMESLOT_SECRET_KEY_BASE=<openssl-rand-base64-64>
TYMESLOT_DATA_ENCRYPTION_KEY=<generate-per-tymeslot-docs>
SCHEDULING_SMTP_USER=<existing-authorized-gmail-address>
SCHEDULING_SMTP_PASSWORD=<google-app-password>
TYMESLOT_GOOGLE_CLIENT_ID=
TYMESLOT_GOOGLE_CLIENT_SECRET=
```
Use a verified upstream release tag; check Tymeslot documentation for the exact encryption key format before starting. The key must be retained in backup and restoration. To run:
```bash
cd ~/RootedOps
sudo docker compose --env-file .env -p rootedops-scheduling -f docker/scheduling/tymeslot.compose.yml config --quiet
sudo docker compose --env-file .env -p rootedops-scheduling -f docker/scheduling/tymeslot.compose.yml up -d
sudo docker compose --env-file .env -p rootedops-scheduling -f docker/scheduling/tymeslot.compose.yml ps
```
Configure Google OAuth callback `https://schedule.rootedpsyche.org/auth/google/callback`, then explicitly select calendars used for conflict detection. Test confirmation and cancellation mail. Disable open admin registration after setup.

## Rallly
Use the official production bundle at https://github.com/lukevella/rallly-selfhosted, not an improvised single-container image:
```bash
cd ~/RootedOps
git clone https://github.com/lukevella/rallly-selfhosted.git docker/scheduling/rallly-selfhosted
cd docker/scheduling/rallly-selfhosted
./rallly.sh setup
```
Set the upstream Rallly environment: `DOMAIN=poll.rootedpsyche.org`, `PROXY_MODE=external`, `WEB_PORT=127.0.0.1:3003`, `NEXT_PUBLIC_BASE_URL=https://poll.rootedpsyche.org`, `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_SECURE=false`, and `SMTP_USER`/`SMTP_PWD` using the authorized Gmail address/app password. Keep generated `SECRET_PASSWORD` and storage credentials private. Review upstream startup/help output before invoking `./rallly.sh start`.

The upstream checkout is a host-local working directory and should remain untracked; do not git-add it to RootedOps. Pin the upstream revision during deployment.

## Host Nginx
After DNS resolves to Linode, copy each config from `nginx/` to `/etc/nginx/sites-available/`, symlink into `sites-enabled`, run `sudo nginx -t && sudo systemctl reload nginx`, then run `sudo certbot --nginx -d poll.rootedpsyche.org -d schedule.rootedpsyche.org`. Check that both HTTP services listen only on localhost.

## Pre-production gates
Verify `docker compose ps`, service logs, TLS, outbound Gmail SMTP delivery, date polls, booking conflict detection, Google Meet creation, and backup/restore of both stacks. Rallly Postgres/Garage and Tymeslot data/Postgres volumes are **not yet covered** by the RootedOps backup scripts. Do not treat this initial bootstrap as production-ready.
