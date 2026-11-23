# SnappyMail — optional multi-provider webmail

SnappyMail is a **webmail client**, not an SMTP server or mailbox host. It uses IMAP to read mail and SMTP submission to send through the actual providers. Do not change MX/SPF/DKIM/DMARC for this deployment. This feature is opt-in and is not a replacement for the existing Rooted Psyche Google Workspace service.

## Scope and prerequisites

* Existing private RootedOps `.env` file. Add the `SNAPPYMAIL_*` keys from `.env.example`, without replacing other secrets.
* DNS A/AAAA for all nine `mail.` subdomains of the managed domains pointing at the same RootedOps host: `mail.dankmushrooms.net`, `mail.danks.farm`, `mail.danks.net`, `mail.danks.services`, `mail.danks.store`, `mail.edanks.com`, `mail.rootedpsyche.com`, `mail.rootedpsyche.net`, `mail.rootedpsyche.org`. These are browser access aliases, **not** email/MX records. Use `nginx/production/snappymail.conf` for all nine names. The staging config `nginx/snappymail.conf` stays test-only to satisfy RootedOps production-host safety checks. A wildcard DNS record does **not** create a matching TLS certificate: install a trusted certificate (or certificates) covering each browser hostname before login. Validate certificate issuance separately for all nine.
* Host Nginx and Certbot. Deploy only over valid HTTPS before entering any mail credentials.
* An operational mailbox provider for each address. Gmail accounts remain with Google; `@rootedpsyche.org` remains on Workspace; `@dankmushrooms.net` requires separate mailbox hosting such as Purelymail or Zoho. SnappyMail itself creates **no** mailboxes.
* Review the pinned SnappyMail image tag against the available `djmaze/snappymail` Docker Hub tags before deployment; do not silently upgrade to latest.

## Deploy

1. Confirm `SNAPPYMAIL_HTTP_PORT=8888` is not used by another service. The compose service is localhost-only and uses the `mail` profile.
2. From the RootedOps root:
   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml --profile mail config --quiet
   docker compose --env-file .env -f docker/docker-compose.yml --profile mail pull snappymail
   docker compose --env-file .env -f docker/docker-compose.yml --profile mail up -d snappymail
   # A freshly started container may need initialization; check logs/status before probing.
   docker ps --filter name=snappymail
   docker logs --tail 80 snappymail
   curl -v --max-time 10 http://127.0.0.1:8888/
   ```
3. Review `nginx/production/snappymail.conf` (or staging-only `nginx/snappymail.conf`), copy/symlink the appropriate file into the host's Nginx sites configuration according to existing RootedOps practice, and enable HTTPS with the host's existing Certbot procedure. Test `sudo nginx -t` before reloading.
4. Confirm each of the nine listed `https://mail.*` hostnames serves the same instance over valid HTTPS. Browser sessions may remain separate across hostnames: test login and logout independently on each host. Do **not** enter a mailbox password before HTTPS is working.
5. From the host, locate SnappyMail's generated initial admin password within the **persistent Docker volume**, following the installed version's admin documentation. Open `https://mail.danks.store/?admin`, rotate the admin password immediately, and secure access to the admin interface. Never commit credentials, tokens, or generated data.
6. Configure only approved IMAP/SMTP domains, with TLS certificate validation enabled and secure IMAP (usually port 993) and SMTP submission (usually port 465 or 587). Avoid allowing arbitrary domains or server overrides. Restrict use to approved staff accounts (an allowlist/authentication control in front of the site is recommended); a list of supported mail domains is **not** a staff-user allowlist.

## Provider configuration and acceptance

| Address domain | Where mail lives | SnappyMail login |
| --- | --- | --- |
| `gmail.com` | Personal Google accounts | Google OAuth2 login extension, where supported |
| `rootedpsyche.org` | Google Workspace for Nonprofits | Google IMAP/SMTP via OAuth2 or a specifically permitted Workspace authentication method |
| `dankmushrooms.net` | External business mail provider (TBD) | Provider IMAP/SMTP credentials |

For Gmail, prefer the upstream **Login GMail OAuth2** extension and follow its documented Google Cloud app setup and consent/security requirements. OAuth setup may require a new project/client, approved redirect URI, verified scopes and testing/publishing; do not reuse scheduling OAuth scopes or secrets without explicit review. The Gmail extension's multi-account/add-account interaction has had historical limitations; validate sign-in and switching with one pilot account for each provider before enrolling all staff. Google app passwords may be unavailable for some managed accounts; do not assume Workspace allows them. The Gmail mobile app can separately add external IMAP accounts without running through SnappyMail.

For the Dank Mushrooms mailbox provider, verify the actual IMAP/SMTP hostname, ports, encryption, authentication, sending identity and deliverability *with the chosen provider*, not by guessing from the email domain. SnappyMail does not confer permission to impersonate alternate From addresses.

Acceptance: all nine HTTPS hostnames resolve to the same instance, with no cross-user account leakage; send and receive a message from each of the three provider categories; test reply, attachments, Sent folders, account switching, logout, mobile client access, and session isolation between two different people. Treat unified Gmail login/switching as unproven until tested.

## Persistence, backups and operational care

SnappyMail's `/var/lib/snappymail` configuration/session data is in the `snappymail_data` Compose volume (typically `docker_snappymail_data`). The format-2 recovery inventory explicitly declares the optional `snappymail` service group and `volumes/snappymail_data.tgz` archive. If the service is installed but its mount is absent, or an orphaned SnappyMail volume exists without its container, backup capture fails instead of falsely reporting a complete recovery. The backup inventory validates the expected archive and includes the deployed image in its image recovery plan. SnappyMail is stopped during the coordinated backup like other application clients; it is resumed if it was previously running. The full isolated recovery process restores the named volume before launching apps, preserving its opt-in profile; `backup/restore-stack.sh` separately restores the volume only to a new target container.

After merging, run a read-only image/volume plan, then a complete backup in a maintenance window (never a partial export). Inspect the **private** `meta/recovery-bundle.json` for `snappymail` installed and `volumes/snappymail_data.tgz` listed in both volumes and required_payloads. Confirm the archive exists in the timestamped backup and is verified by checksum. Rehearse restoration on an isolated clean host before asserting recovery acceptance. Do not upload this archive to GitHub or share OAuth tokens and credentials. It does **not** back up messages held on Gmail, Workspace, or Purelymail. Do not delete or recreate the volume during application updates.

Keep SnappyMail patched, restrict its domain connections and public admin exposure, and review upstream security advisories. If disabling the service, stop only `snappymail`; leave other RootedOps services running.

## Rollback

```bash
docker compose --env-file .env -f docker/docker-compose.yml --profile mail stop snappymail
```

Disable the new Nginx site if necessary. Preserve the named data volume for later recovery. No existing mail DNS, mailboxes, or other containers need be altered.
