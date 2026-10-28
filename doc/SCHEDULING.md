# Rooted Psyche scheduling — Issue #17

Public endpoints: Rallly https://poll.rootedpsyche.org; Tymeslot https://schedule.rootedpsyche.org. DNS records have been added by the operator. The external host Nginx/Certbot setup is still required. Deploy directly from RootedOps `main`; no feature branch.

## SMTP: reuse the Listmonk Gmail pattern

Listmonk already used Gmail SMTP; scheduling uses the same provider but a **separate Google app password** for Tymeslot. Authentication user: `rootedpsyche@gmail.com`. SMTP: `smtp.gmail.com`, port `587`, STARTTLS, password authentication. Use the same authorized email address as sender. Never commit app passwords. Google OAuth *client secret* is unrelated to Gmail SMTP *app password*.

Open https://myaccount.google.com/apppasswords signed into `rootedpsyche@gmail.com`. Under the current interface, enter an app label such as `Tymeslot`, choose **Create**, and securely copy the generated 16-character app password (often displayed as four groups of four characters). The historic **Select app → Other → Create → Done** instructions refer to an older interface; follow the current prompts. App passwords generally require 2-Step Verification and may not be available on all accounts. Keep Listmonk's existing app password unchanged.

Rallly needs its own `SMTP_USER` and `SMTP_PWD` in its **separate** upstream `.env`. Prefer a separate labeled Google app password for Rallly, too. Google SMTP usage limits mean this setup is appropriate for modest volumes, not bulk delivery.

## Tymeslot: existing Docker installation

User confirmed `luka1thb/tymeslot:1.6.0` pulled and `rootedops-tymeslot` started successfully using `docker/scheduling/tymeslot.compose.yml`. This only establishes container start; email delivery, OAuth and external routing remain untested. Environment keys in the RootedOps root `.env.example` must be mirrored into the untracked root `.env`:

```dotenv
TYMESLOT_IMAGE_TAG=1.6.0
TYMESLOT_SECRET_KEY_BASE=<generated-secret>
TYMESLOT_DATA_ENCRYPTION_KEY=<generated-encryption-key>
SCHEDULING_SMTP_USER=rootedpsyche@gmail.com
SCHEDULING_SMTP_PASSWORD=<Tymeslot-specific-Gmail-app-password>
TYMESLOT_GOOGLE_CLIENT_ID=<OAuth-web-client-ID>
TYMESLOT_GOOGLE_CLIENT_SECRET=<OAuth-web-client-secret>
TYMESLOT_GOOGLE_STATE_SECRET=<random-state-signing-secret>
TYMESLOT_ENABLE_GOOGLE_AUTH=false
```

Generate secrets once and preserve them across upgrades and restores:

```bash
openssl rand -base64 64    # SECRET_KEY_BASE
openssl rand -base64 48    # DATA_ENCRYPTION_KEY; check exact requirements for pinned image
openssl rand -hex 32       # GOOGLE_STATE_SECRET
```

Avoid regenerating the encryption key when upgrading or restoring. `TYMESLOT_ENABLE_GOOGLE_AUTH=false` hides Google account sign-in but still allows Calendar and Meet OAuth integrations.

### Configure Google Cloud

Reference: https://tymeslot.app/docs/google-oauth and https://support.google.com/cloud/answer/15544987

1. Sign in to https://console.cloud.google.com as the account administering the OAuth project. Select or create a project (e.g., Rooted Psyche Scheduling).
2. Under **APIs & Services → Library**, enable **Google Calendar API** and **Google Meet API**. Google People API is not needed for Tymeslot.
3. Open **Google Auth Platform**. For a new app, choose **Get started**, enter app name, support email, and developer contact under **Branding**. Set **Audience → External** for a personal `@gmail.com` account; Internal is for an eligible Google Workspace organization.
4. Under **Data Access**, configure required scopes as Tymeslot documents (Calendar requires `https://www.googleapis.com/auth/calendar`; Meet scope is requested by Tymeslot when needed). Do not guess extra broad permissions. Google's interface may defer scope consent until actual connection; use the product's documented scopes.
5. Under **Audience → Test users**, add `rootedpsyche@gmail.com` (and any other administrator who must authorize during testing). In Testing, OAuth access/refresh tokens with Calendar scopes generally expire after **7 days**; evaluate production publishing and Google's verification requirements before relying on uninterrupted synchronization.
6. Under **Clients**, create an **OAuth client ID → Web application**. The following **three exact authorized redirect URIs** are required for Tymeslot's separate flows:
   - `https://schedule.rootedpsyche.org/auth/google/callback` (optional Google login)
   - `https://schedule.rootedpsyche.org/auth/google/calendar/callback` (Calendar)
   - `https://schedule.rootedpsyche.org/auth/google/video/callback` (Meet)
7. Copy client ID and client secret into the untracked RootedOps `.env`, alongside the generated `TYMESLOT_GOOGLE_STATE_SECRET`. Restart Tymeslot after updates. HTTPS/Certbot must be working for Google OAuth redirects.
8. In Tymeslot, connect the Google Calendar account, explicitly select calendars for conflict checking and where bookings are written, and enable Google Meet on the event type. Test a busy slot being blocked and a successful event/Meet booking. Google account authentication and calendar authorization are separate operations.

CLI to apply new Compose environment without touching ERPNext:

```bash
cd ~/RootedOps
git pull --ff-only origin main
sudo docker compose --env-file .env -p rootedops-scheduling -f docker/scheduling/tymeslot.compose.yml config --quiet
sudo docker compose --env-file .env -p rootedops-scheduling -f docker/scheduling/tymeslot.compose.yml up -d --no-deps tymeslot
sudo docker compose --env-file .env -p rootedops-scheduling -f docker/scheduling/tymeslot.compose.yml ps
sudo docker logs --tail 100 rootedops-tymeslot
curl -I http://127.0.0.1:4000
```

Do not paste resolved `docker compose config` (without `--quiet`) or container environment into public issue comments; they contain secrets.

## First administrator and Google sign-in (Tymeslot)

The **first registered user** in a new Tymeslot database is automatically administrator; there is no default username/password. Use the intended Rooted Psyche administrator account (`rootedpsyche@gmail.com`) to register, preferably using Google Sign-In after OAuth is configured. After registration open `https://schedule.rootedpsyche.org/admin` and disable public registration. If another user registered first, use the documented Tymeslot release admin promotion command rather than resetting the database.

To enable the Google sign-in button set `TYMESLOT_ENABLE_GOOGLE_AUTH=true` in RootedOps root `.env` and rerun:

```bash
cd ~/RootedOps
sudo docker compose --env-file .env -p rootedops-scheduling -f docker/scheduling/tymeslot.compose.yml up -d --no-deps tymeslot
```

The OAuth client supports login, Calendar, and Meet, but each uses a distinct registered redirect URI. Environment variables override admin-UI controls for the same setting.

## Deployment verification (2026-10-28)

The operator confirmed Tymeslot 1.6.0 running with HTTP 302 to `/auth/login`, active background jobs and no observed startup error. Host Nginx validated and reloaded; Certbot installed HTTPS on both scheduling domains, with certificate expiry 2027-01-26 and scheduled renewal. Google OAuth redirect links were added by the operator. Neither Google login nor SMTP delivery has yet been end-to-end verified.

Rallly initial `./rallly.sh start` failed on Docker socket permission denied (`unix:///var/run/docker.sock`). This is a Docker access problem, **not** evidence of broken Rallly services. From the upstream checkout try:

```bash
cd ~/RootedOps/docker/scheduling/rallly-selfhosted
sudo ./rallly.sh start
sudo ./rallly.sh status
```

Use `sudo` for both so the Docker commands can access the daemon; an unprivileged `./rallly.sh status` may fail even if the stack is running. Do not loosen Docker socket permissions with `chmod 666`. Be cautious if `sudo` changes ownership of files in the checkout. The upstream script may warn `ACME_EMAIL` is unset under external proxy mode; host Certbot manages the public certificates, so that alone is not a blocker. Inspect `sudo docker ps` and logs if startup still fails.

## Rallly is already a Docker deployment

The official https://github.com/lukevella/rallly-selfhosted project provides **Docker Compose**, not an application that has to be rebuilt. It launches the published Rallly web image, PostgreSQL, Garage object storage, and (by default) Traefik. **We do not need to create a custom Dockerfile/image.** Keep the upstream Compose bundle intact to ease maintenance.

Manual installation managed from the RootedOps local checkout:

```bash
cd ~/RootedOps
git clone https://github.com/lukevella/rallly-selfhosted.git docker/scheduling/rallly-selfhosted
cd docker/scheduling/rallly-selfhosted
./rallly.sh setup
```

Configure its locally generated `.env` with:

```dotenv
DOMAIN=poll.rootedpsyche.org
PROXY_MODE=external
WEB_PORT=127.0.0.1:3003
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USER=rootedpsyche@gmail.com
SMTP_PWD=<Rallly-specific-Gmail-app-password>
SUPPORT_EMAIL=rootedpsyche@gmail.com
NOREPLY_EMAIL=rootedpsyche@gmail.com
```

With external proxy mode, Rallly's bundled Traefik will not claim host ports 80/443. Rallly derives `NEXT_PUBLIC_BASE_URL=https://poll.rootedpsyche.org` from DOMAIN. Preserve upstream-generated secret/storage credentials; do not commit the nested checkout or its `.env`. Pin/check its upstream revision. Start from the directory with `./rallly.sh start`, then check `./rallly.sh status` and logs.

## Host Nginx and Certbot (not yet installed)

Both services bind only to loopback (`127.0.0.1:3003` for Rallly and `127.0.0.1:4000` for Tymeslot). Copy the RootedOps `nginx/rallly.conf` and `nginx/tymeslot.conf` virtual hosts into `/etc/nginx/sites-available/` and enable them:

```bash
cd ~/RootedOps
sudo cp nginx/rallly.conf /etc/nginx/sites-available/rallly.conf
sudo cp nginx/tymeslot.conf /etc/nginx/sites-available/tymeslot.conf
sudo ln -sfn /etc/nginx/sites-available/rallly.conf /etc/nginx/sites-enabled/rallly.conf
sudo ln -sfn /etc/nginx/sites-available/tymeslot.conf /etc/nginx/sites-enabled/tymeslot.conf
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d poll.rootedpsyche.org -d schedule.rootedpsyche.org
```

Run Nginx checks before requesting certificates, and confirm DNS points to the Linode. Then test both public endpoints and TLS renewal.

## Production acceptance / restore

Before treating either service as production-ready: verify SMTP login and delivery, board poll responses, calendar conflict prevention, participant booking and cancellation, Google Meet link creation, and persisted records after a restart. Check Linode capacity. Backups currently **do not include** the newly created Tymeslot volumes or the Rallly Postgres/Garage data; extend RootedOps backup/restore scripts and test a restore, including OAuth/encryption keys. Keep all booking fields minimal; sensitive participant agreements remain in SignatureGate.

## October 28 operational follow-up: startup, permissions, one-organizer Rallly

- Rallly's official self-hosted Compose services (`web`, `db`, `garage`) specify `restart: always`; after `sudo ./rallly.sh start` they return on Docker daemon/server reboot without a recurring host cron or systemd script. Verify via `sudo docker ps` and `sudo docker inspect <container> --format '{{.HostConfig.RestartPolicy.Name}}'`.
- Rallly SMTP magic-code delivery was successfully verified by the operator using `ray@edanks.com`. Initial administrative identity is that account; `SUPPORT_EMAIL` and `SMTP_USER` are independent of organizer/login identity. The upgrade prompt for additional workspace **members** does not mean poll respondents need accounts or paid seats. Rallly is intended to have exactly one organizer account for Rooted Psyche, with board directors participating as guest voters.
- Before changing existing Rallly admin email, check logged-in user profile and `/control-panel` user management for a supported change/transfer. `INITIAL_ADMIN_EMAIL` selects the initial administrator; do not assume altering it retroactively renames an established account. If starting fresh and no polls exist, preserve credentials and take a database backup first; use only supported UI mechanisms or documented controlled reinitialization, never ad-hoc database deletes.
- Tymeslot Google login and the organization's Google Calendar authorization were successfully exercised by the operator. Its current Calendar integration requests full `https://www.googleapis.com/auth/calendar` scope, which includes permanent deletion of calendars. This is broader than ideal but is required by Tymeslot's present implementation. **Public appointment attendees do not authorize Google Calendar**; only organizers connecting calendars do. Record a least-privilege improvement for the upstream provider or a future integration change, not an untested scope override in Google Cloud.
- For embedding a Tymeslot booking page on WordPress, the official `https://tymeslot.app/docs/embed` recommends inline embed and requires whitelisting the WordPress host at `Dashboard → Embed & Share → Security`. The official Tymeslot WordPress plugin is also available. A potential BookWorks-managed WordPress publication for office appointments is a separate follow-on scope, pending a concrete publication decision. Do not add booking data collection to WordPress; send it to Tymeslot.
