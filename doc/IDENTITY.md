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

## Architecture decision — organizational role authorization (2026-11-27)

**This is the current target architecture.** It supersedes the *proposed* Google source consolidation steps in [IDENTITY-ONBOARDING.md](IDENTITY-ONBOARDING.md). **Do not change the three working Google sources, clients, source-link records, or MailFlow application policies as part of this decision.** A single Google button with multiple linked Google accounts per authentik person is not supported by the tested stock authentik 2026.8.7 source-connection workflow; simplifying Google login is deferred, not a prerequisite for application integration.

### Identity, roles, access, and mailboxes are distinct

- **Person / identity:** One authentik user represents a human and may link multiple sign-in methods. Existing `RayDanks` uses both `ray@edanks.com` and `raymonddanks@gmail.com` to access the **same** MailFlow account. A future `ray@rootedpsyche.org` sign-in can be linked to this person only after correcting the verified-email marker for multi-source linking; `admin@rootedpsyche.org` remains a separate pilot identity. Do not merge automatically by email.
- **Organizational roles:** Authentik groups represent assignments such as Rooted Psyche **board director** and **Spiritual Practitioner**, and Dank Mushrooms **cultivation** or **sales**. One person may hold multiple roles across organizations. Role assignment/revocation is centrally administered in authentik rather than independently adding/removing the person inside every application.
- **Application entitlements:** authentik applications authorize access using those organizational groups. A board director may have MailFlow and board-portal access without automatically gaining Appsmith access; a Spiritual Practitioner may receive MailFlow and scoped Appsmith access without board access. A role may grant more than one application's access. Do not confuse application sign-in with app-internal capabilities or data scope.
- **MailFlow eligibility:** keep the **currently working** automatic verified `edanks.com`/`rootedpsyche.org` Workspace admission and passwordless OIDC user creation, with `mailflow-users` for approved exceptions. The user explicitly accepts Workspace mailbox retirement plus account/role offboarding as the first operational model. A verified organizational address is MailFlow eligibility, **not** automatic board or practitioner role membership.
- **Mailbox credentials:** independently attached IMAP/SMTP/app-password or mailbox OAuth credentials in MailFlow are *not* authentik authentication methods and do not establish organization roles.

### WordPress is the next application integration

For the Rooted Psyche WordPress board portal, authentik is the **source of truth** for board-director membership and thus board access. WordPress will still enforce its own roles/capabilities at request time; the SSO integration must **derive/synchronize the existing WordPress `board_director` role** from a trusted authentik group/claim (or reliable provisioning mechanism) and revoke it when removed. It must never require operators to maintain a *separate* manual board-members list in WordPress.

Prior to cutover, inventory current miniOrange Google SSO, Members plugin roles, board page authorization, existing WP user IDs and current admin recovery path; verify the exact miniOrange plugin edition supports the required OIDC/SAML role/group mapping and **revocation on subsequent login**. If it does not, implement an explicitly scoped server-side mapping/provisioning method and test it; do not assert that simply configuring an OIDC provider enforces group authorization.

**Acceptance:** (1) existing board director logs in through authentik and keeps the **same WP user** and board access, (2) authenticated Spiritual Practitioner without board role is denied board content, (3) removing the authentik board-director group revokes WordPress board capability on the next validated sync/login *and prevents access from existing sessions*, (4) unrelated role assignments and administrator recovery remain intact. Non-board users may still authenticate to the public site where intended, but must not acquire board privileges.

**Offboarding:** disable/remove former org Workspace account, revoke relevant authentik organizational groups and application entitlements, invalidate relevant application sessions, and remove mapped WP capability; retain any other legitimately active organizational affiliations/identities. Review MailFlow accounts/mailboxes separately. Until automatic synchronization and session invalidation are verified, keep a documented manual removal step as a safety fallback.

Tracked in [RootedOps #139](https://github.com/RayzorDuff/RootedOps/issues/139). Operational plan: [IDENTITY-ONBOARDING.md](IDENTITY-ONBOARDING.md).
