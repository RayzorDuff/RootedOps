# MailFlow — optional unified webmail

MailFlow is an IMAP/SMTP **client**, not a mailbox server. The existing nine mail.* hostnames, certificates, mail providers and MX records are retained. The canonical URL is `https://mail.danks.store`, and this URL is the only one to use for first registration and Google OAuth callbacks. Redirect alternate public mail hostnames to the canonical URL at the host's HTTPS Nginx layer to avoid cross-origin session issues.

## Cutover from SnappyMail (same DNS and Nginx upstream port)

1. Before removing SnappyMail, capture a **verified pre-cutover backup** using the previous RootedOps commit, or archive `docker_snappymail_data` separately. Keep this archive until MailFlow recovery is verified. Older backups must be restored with the prior RootedOps recovery revision; formats differ.
2. Update RootedOps. Preserve the deployed host Nginx Certbot-generated HTTPS config and `/etc/letsencrypt/live/snappymail` certificate (it covers the *hostnames*, even if its certificate name remains snappymail). Do **not** replace the live HTTPS config with the repository's HTTP-only template; use `nginx/production/mailflow.conf` as the application routing reference. Nginx already proxies port 8888; that port remains unchanged. No DNS, MX, or TLS issuance is required.
3. Copy `MAILFLOW_*` from `.env.example` into the **private** `.env`. Generate `MAILFLOW_SESSION_SECRET` and `MAILFLOW_ENCRYPTION_KEY` using `openssl rand -hex 32`, and `MAILFLOW_DB_PASSWORD` using `openssl rand -hex 16`. Retain these exact values in the private backup; changing the encryption key makes stored account credentials unreadable. Never commit them.
4. Stop/remove only the old container, not its Docker volume: `sudo docker stop snappymail && sudo docker rm snappymail`. Do not use `docker compose down -v` or `--remove-orphans`: other WordPress containers are operated separately.
5. Run:
   ```bash
   sudo docker compose --env-file .env -f docker/docker-compose.yml --profile mail pull mailflow-postgres mailflow-backend mailflow-frontend
   sudo docker compose --env-file .env -f docker/docker-compose.yml --profile mail up -d mailflow-postgres mailflow-backend mailflow-frontend
   sudo docker ps --filter name=mailflow
   curl -fsSI http://127.0.0.1:8888/
   curl -fsSI https://mail.danks.store/
   ```
6. Register the first user immediately (it becomes administrator), then disable open registration. Validate HTTPS forwarding, secure sessions, attachment handling, separate account switching, and the sender identity per account.
7. Configure Google or IMAP accounts under MailFlow Settings → Accounts / Email providers. Google callback is `https://mail.danks.store/oauth/google/callback`. Two *separate* Google Workspace Internal OAuth projects do not automatically fit in a single MailFlow Google client configuration; verify support before claiming cross-tenant OAuth. Personal Gmail also cannot authorize using an Internal Workspace client. Purelymail uses the provider's IMAP/SMTP settings, not DNS changes.

## Backups and restore

RootedOps treats `mailflow-postgres`, `mailflow-backend`, and `mailflow-frontend` as one optional installed group. Its backup stops mail clients and stores the database as a consistent **logical dump** (`db/mailflow-postgres.sql.gz`), not a copy of the live PostgreSQL volume. Full recovery requires the private `meta/.env` encryption/session secrets along with the SQL dump. An orphaned `mailflow_postgres_data` volume or partial service group fails backup inventory rather than silently skipping data. The legacy SnappyMail volume is not part of new backups; keep a separate pre-cutover archive for historical restoration.

Before cutover or data deletion, test fresh-host restoration and all user account credentials. The existing HTTPS site may still be named `snappymail` in `/etc/nginx/sites-enabled` because Certbot managed that filename: do not delete it without first installing a replacement HTTPS site.

## RootedOps SSO (authentik)

First successful Google Workspace → authentik → MailFlow account login was validated on 2026-11-26. Refer to [IDENTITY-ONBOARDING.md](IDENTITY-ONBOARDING.md) for separate administrator and invited-user checklists, verified email scope mapping, account-linking steps, safe diagnostics and the planned automation. Keep **SSO login** (OIDC `openid email profile`) separate from **connecting mailboxes** (Gmail scope or supported app password, or third-party IMAP/SMTP). Link an existing MailFlow account through Settings → Security → Linked SSO accounts before relying on federated login. Do not change MailFlow to public/open SSO provisioning during this stage.
