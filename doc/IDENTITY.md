# RootedOps identity service — authentik 2026.8.7

**Scope:** First identity milestone for [#139](https://github.com/RayzorDuff/RootedOps/issues/139). Do not treat this deployment as completing MailFlow SSO, WordPress identity linking, or Workspace mailbox OAuth. This is the **open-source** authentik edition; the paid Google Workspace **provider/provisioning** feature is not needed for upstream Google **login**.

## Deployment prerequisites / safety

- Preserve existing MailFlow local administrator login and WordPress miniOrange Google SSO until the replacement is proven.
- Create/verify `auth.danks.store` DNS, host Nginx TLS certificate and a proxy from HTTPS to `127.0.0.1:${ROOTEDOPS_AUTHENTIK_HTTP_PORT:-9092}`. `nginx/authentik.conf` is **HTTP-only reference**; never expose passwords over HTTP or replace a Certbot-managed HTTPS server with that template.
- Add the five `ROOTEDOPS_AUTHENTIK_*` values from `.env.example` to the **private** `.env`. Independently generate the DB password and signing secret (for example `openssl rand -hex 32`). Do not commit, rotate casually or print secrets. The same signing key and PostgreSQL snapshot are required for recovery.
- Containers are opt-in (`identity` profile); binding is loopback-only; dedicated internal Docker network. No worker Docker socket mount, so automatic outpost container provisioning is **not enabled**. Outposts, if later required, must be explicitly managed.
- Version pinned to upstream 2026.8.7. Do not add Enterprise license keys or depend on paid source-stage embedding / Workspace directory provisioning.

## First install

```bash
cd ~/RootedOps
# Fail closed if identity-only secrets were not configured; never print them.
set -a
source .env
set +a
: "${ROOTEDOPS_AUTHENTIK_DB_PASSWORD:?Set identity DB password in .env}"
: "${ROOTEDOPS_AUTHENTIK_SECRET_KEY:?Set identity signing key in .env}"
sudo docker compose --env-file .env -f docker/docker-compose.yml --profile identity config --quiet
sudo docker compose --env-file .env -f docker/docker-compose.yml --profile identity pull authentik-postgres authentik-server authentik-worker
sudo docker compose --env-file .env -f docker/docker-compose.yml --profile identity up -d authentik-postgres authentik-server authentik-worker
sudo docker ps --filter name=authentik
curl -fsSI http://127.0.0.1:9092/
```

Verify TLS and complete authentik's initial admin setup at `https://auth.danks.store/if/flow/initial-setup/` (or follow the installed version's redirect). Create and protect the local break-glass admin first; require MFA. Configure outbound SMTP for recovery alerts before relying on login for other apps. No public sign-up unless specifically invited.

## Phase 1: edanks.com Workspace identity and existing MailFlow account

1. Create a **Google OAuth source** in authentik (Directory → Federation and Social login) with identity-only scopes `openid email profile`. Use a new identity-only Google Cloud OAuth client; do **not** reuse MailFlow's restricted Gmail mailbox client.
2. Set authentik callback URL to the exact URL supplied by the Google source UI (normally `https://auth.danks.store/source/oauth/callback/<source-slug>/`). Limit logins to approved identities (initially `ray@edanks.com`), not every Google user.
3. Add source to authentik's default identification/login stage. Sign in and verify the existing authentik principal and externally linked Google identity. Do not auto-merge based on email alone. Validate logout, MFA, recovery and audit.
4. In authentik Applications → Providers create an OAuth2/OpenID Connect provider for MailFlow; configure redirect URI from **MailFlow Settings → SSO** and OIDC discovery URL provided by authentik. Grant only `mailflow-users` access.
5. MailFlow already has a local personal user. Use MailFlow's existing *authenticated* identity-linking workflow (it requires recent reauthentication) to link the authentik provider to that user **before** using the SSO button on the login screen. Verify a Google login returns to the same MailFlow user UUID and the same mailboxes. Keep password login and break-glass admin until tested.
6. Do not confuse this identity-only OAuth permission with connecting `ray@edanks.com`'s Google mailbox (which needs Gmail scope or approved app password).

## Phase 2: Rooted Psyche board / personal Gmail

- Configure distinct sources for organizational `rootedpsyche.org` Google Workspace identities and personal Google users. An External *identity-only* client can serve Gmail identities without Gmail mail access scopes; Workspace admins may enforce OAuth app controls.
- **Invitation-only** linking with explicit human verification and organization authorization. No board role inferred solely from `@rootedpsyche.org` domain.
- Existing Rooted Psyche WordPress: maintain the current miniOrange SSO and `board_director` / Members role mapping until a read-only user audit and tested account-linking runbook. Test the authentik-supported free `OpenID Connect Generic Client` plugin in isolation; avoid duplicate WordPress user creation and confirm no fee-gated behavior. Do not grant admin or board permissions to new OIDC-created accounts by default.
- Allow a board member to link a personal Google identity and a Rooted Psyche identity to **one** authentik person and one WordPress user, after verified linking. Then allow OIDC into MailFlow as a separately authorized application.
- Only after board and MailFlow acceptance, plan Appsmith/ERPNext and business mail provisioning. Separate projects/issues for restricted Gmail mailbox OAuth and organization mailbox entitlements.

## Recovery

RootedOps nightly recovery inventory includes the **complete three-container identity group**: `authentik-postgres`, `authentik-server`, `authentik-worker`. Backups pause server+worker, logically dump PostgreSQL to `db/authentik-postgres.sql.gz`, and archive shared `/data` and worker `/certs` named volumes. PostgreSQL's live raw volume is **not** tarred. Private `meta/.env` includes the signing secret. A partial group or orphan identity volume fails closed. Restores reject an existing authentik database container and require a clean host.

After first production deployment, take a **full RootedOps backup and test an isolated restore** before moving any other service's login to authentik. Validate user identities and signing keys after recovery; do not use `docker compose down -v` or `--remove-orphans` on the shared host.

## Verified production milestone — 2026-11-26

**Validated:** `ray@edanks.com` authenticates through the `google-edanks` Google Workspace source into authentik's `RayDanks` internal user; MailFlow 4.5.1 accepts an OIDC login from authentik and returns the *existing* MailFlow user `ray@edanks.com`. Existing MailFlow identities and connected mailboxes were retained. The tested configuration was completed through the administration UIs; it is **not yet managed by a reproducible provisioning job**.

- Authentik: `https://auth.danks.store` (self-hosted OSS 2026.8.7), local break-glass `akadmin`, personal federated user `RayDanks`.
- OAuth source: Google Workspace — edanks.com, slug `google-edanks`, callback `https://auth.danks.store/source/oauth/callback/google-edanks/`, identity-only Google scopes.
- Authentik application slug `mailflow`, confidential OIDC provider, exact redirect `https://mail.danks.store/auth/oidc/rootedops/callback`, standard scopes `openid email profile`. Discovery: `https://auth.danks.store/application/o/mailflow/.well-known/openid-configuration` (issuer must match discovery).
- MailFlow Settings → Administration → Single Sign-On: provider `RootedOps Identity`, slug `rootedops`, verified email required, insecure connections disabled, **Match existing / login_existing_only** provisioning; preserve local password. MailFlow Settings → Security → Linked SSO accounts links `ray@edanks.com` to this provider.
- Authentik default email claim returned `email_verified: false`, leading MailFlow to reject login **even though linking succeeded**. A custom scope mapping `RootedOps - Verified Email` with scope `email` resolved this once the verified address was stored as a **top-level** authentik user attribute. Do not set `email_verified: True` globally or disable MailFlow's verified-email requirement.

For detailed first-user/next-user procedures, see [IDENTITY-ONBOARDING.md](IDENTITY-ONBOARDING.md). For Gmail mailbox OAuth vs identity scopes, see the MailFlow runbook.

### Operations and unresolved acceptance

This initial login **does not** establish general purpose account provisioning, SSO authorization policies for board/staff, a verified email address for every future user, Wordpress migration, or automatic mailbox attachment. Future user onboarding must be invitation-only and organization-approved; email address similarity or Google source selection alone cannot grant another organization's privileges. See [#139](https://github.com/RayzorDuff/RootedOps/issues/139).

## MailFlow SSO admission and passwordless provisioning

See [IDENTITY-MAILFLOW-SSO-PROVISIONING.md](IDENTITY-MAILFLOW-SSO-PROVISIONING.md) for the operator-tested group gate and pending trusted-Workspace domain-wide auto-access policy. MailFlow Open SSO provisioning is appropriate **only** behind a restrictive authentik application binding; public password registration must remain closed.
