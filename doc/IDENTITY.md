# RootedOps identity service — authentik 2026.8.7

**Privacy note:** Any email-like address below is an illustrative, pseudonymous placeholder for a configuration or acceptance test, not an actual user's address. Keep real person-email mappings and invitation recipients in approved private operational systems; do not copy them into public repository docs or issue comments.

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
2. Set authentik callback URL to the exact URL supplied by the Google source UI (normally `https://auth.danks.store/source/oauth/callback/<source-slug>/`). Limit logins to approved identities (initially `primary-user@edanks.com`), not every Google user.
3. Add source to authentik's default identification/login stage. Sign in and verify the existing authentik principal and externally linked Google identity. Do not auto-merge based on email alone. Validate logout, MFA, recovery and audit.
4. In authentik Applications → Providers create an OAuth2/OpenID Connect provider for MailFlow; configure redirect URI from **MailFlow Settings → SSO** and OIDC discovery URL provided by authentik. Grant only `mailflow-users` access.
5. MailFlow already has a local personal user. Use MailFlow's existing *authenticated* identity-linking workflow (it requires recent reauthentication) to link the authentik provider to that user **before** using the SSO button on the login screen. Verify a Google login returns to the same MailFlow user UUID and the same mailboxes. Keep password login and break-glass admin until tested.
6. Do not confuse this identity-only OAuth permission with connecting `primary-user@edanks.com`'s Google mailbox (which needs Gmail scope or approved app password).

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

**Validated:** `primary-user@edanks.com` authenticates through the `google-edanks` Google Workspace source into authentik's `RayDanks` internal user; MailFlow 4.5.1 accepts an OIDC login from authentik and returns the *existing* MailFlow user `primary-user@edanks.com`. Existing MailFlow identities and connected mailboxes were retained. The tested configuration was completed through the administration UIs; it is **not yet managed by a reproducible provisioning job**.

- Authentik: `https://auth.danks.store` (self-hosted OSS 2026.8.7), local break-glass `akadmin`, personal federated user `RayDanks`.
- OAuth source: Google Workspace — edanks.com, slug `google-edanks`, callback `https://auth.danks.store/source/oauth/callback/google-edanks/`, identity-only Google scopes.
- Authentik application slug `mailflow`, confidential OIDC provider, exact redirect `https://mail.danks.store/auth/oidc/rootedops/callback`, standard scopes `openid email profile`. Discovery: `https://auth.danks.store/application/o/mailflow/.well-known/openid-configuration` (issuer must match discovery).
- MailFlow Settings → Administration → Single Sign-On: provider `RootedOps Identity`, slug `rootedops`, verified email required, insecure connections disabled, **Match existing / login_existing_only** provisioning; preserve local password. MailFlow Settings → Security → Linked SSO accounts links `primary-user@edanks.com` to this provider.
- Authentik default email claim returned `email_verified: false`, leading MailFlow to reject login **even though linking succeeded**. A custom scope mapping `RootedOps - Verified Email` with scope `email` resolved this once the verified address was stored as a **top-level** authentik user attribute. Do not set `email_verified: True` globally or disable MailFlow's verified-email requirement.

For detailed first-user/next-user procedures, see [IDENTITY-ONBOARDING.md](IDENTITY-ONBOARDING.md). For Gmail mailbox OAuth vs identity scopes, see the MailFlow runbook.

### Operations and unresolved acceptance

This initial login **does not** establish general purpose account provisioning, SSO authorization policies for board/staff, a verified email address for every future user, Wordpress migration, or automatic mailbox attachment. Future user onboarding must be invitation-only and organization-approved; email address similarity or Google source selection alone cannot grant another organization's privileges. See [#139](https://github.com/RayzorDuff/RootedOps/issues/139).

## MailFlow SSO admission and passwordless provisioning

See [IDENTITY-MAILFLOW-SSO-PROVISIONING.md](IDENTITY-MAILFLOW-SSO-PROVISIONING.md) for the operator-tested group gate and pending trusted-Workspace domain-wide auto-access policy. MailFlow Open SSO provisioning is appropriate **only** behind a restrictive authentik application binding; public password registration must remain closed.

## Architecture decision — organizational role authorization (2026-11-27)

**This is the current target architecture.** It supersedes the *proposed* Google source consolidation steps in [IDENTITY-ONBOARDING.md](IDENTITY-ONBOARDING.md). **Do not change the three working Google sources, clients, source-link records, or MailFlow application policies as part of this decision.** A single Google button with multiple linked Google accounts per authentik person is not supported by the tested stock authentik 2026.8.7 source-connection workflow; simplifying Google login is deferred, not a prerequisite for application integration.

### Identity, roles, access, and mailboxes are distinct

- **Person / identity:** One authentik user represents a human and may link multiple sign-in methods. Existing `RayDanks` uses both `primary-user@edanks.com` and `linked-personal@gmail.example` to access the **same** MailFlow account. A future `linked-user@rootedpsyche.org` sign-in can be linked to this person only after correcting the verified-email marker for multi-source linking; `workspace-admin@rootedpsyche.org` remains a separate pilot identity. Do not merge automatically by email.
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


### Multi-site WordPress SSO architecture — Rooted Psyche and Dank Mushrooms (2026-11-27)

**Implement the reusable integration once and configure it separately on each site.** The first acceptance site is Rooted Psyche; Dank Mushrooms must be considered in shared design/API/claim mapping and tested later before enabling SSO there. This is *not* a site network or shared WordPress database and does not imply identical WordPress login policies.

| Concern | Rooted Psyche WordPress | Dank Mushrooms WordPress / WooCommerce |
|---|---|---|
| Site audience | Public site + protected board portal | Public storefront + native WooCommerce customers |
| authentik population | Approved internal organizational people, including board directors | Approved staff, developers and website operators **only** |
| Non-authentik login | Public visitors; current WP fallback during migration | **All WooCommerce shoppers**, registration, checkout, My Account, password reset and account/profile management |
| Authorization | Authentik board-director group → existing WP `board_director` enforcement; Spiritual Practitioner alone grants no board privilege | Authentik staff/developer/website-admin organizational roles → specifically scoped WP roles/capabilities |
| Onboarding | Explicit organizational assignment, link existing WP user where appropriate | Existing WP administrator/editor accounts matched deliberately; **never** auto-create an authentik principal for a WooCommerce customer |
| Offboarding | Revoke board access and existing WP board sessions | Revoke staff/admin capabilities and sessions **without changing customer records or customer checkout** |

#### Shared WordPress-authentik integration contract

- **One reusable implementation/runbook** should support multiple independent WP deployments. If code is required, build a reusable WordPress integration component/plugin with **per-site configuration**, rather than copying Rooted Psyche-specific hooks into Dank Mushrooms. Reuse claim parsing, stable authentik subject-to-WP-user mapping, session/revocation protections, instrumentation, rollback and tests. Site policies are configuration or explicitly named adapters, not hardcoded global WordPress behavior.
- Use **separate authentik Applications/OIDC Providers and redirect URIs per site**, with distinct client credentials, access policies and claims as necessary. A shared identity directory does **not** imply a shared OAuth client, WordPress user database, user ID, SSO callback or cookie.
- Authentication **must not globally replace `wp-login.php` / WooCommerce authentication flows across all WP users**. Administrative SSO is explicitly routed for eligible staff users; WooCommerce native customer login, registration, account recovery, carts, guest checkout and ERPNext/Woo identity linking remain unaffected. No global login redirect applied to `/my-account`, checkout, WordPress registration or REST/API/webhook traffic.
- A person might also be a customer. Their staff authentik identity and WooCommerce customer account should not be implicitly merged or granted capabilities because of matching email. Role elevation, even for an existing WP user, must require approved authentik organizational assignment and verified matching of a stable subject-to-WP link.
- The shared adapter must enforce **role-to-capability mapping per site**: e.g. `rootedpsyche-board-directors` maps to Rooted Psyche `board_director`, not Dank Mushrooms `administrator`; Dank Mushrooms developer/editor privileges are granted by separate approved role policy only. Never infer WordPress admin rights from a Workspace domain, another site role or MailFlow access.
- Verify **role revocation for already logged-in WordPress staff** and define maximum revocation latency, with emergency revocation and local admin recovery. Preserve existing local WordPress/WooCommerce accounts, order ownership, customer IDs, ERPNext links, and front-end session continuity. Restrict changes to trusted admin SSO paths.
- Before coding, inventory BOTH installed WordPress sites and relevant plugins, current login flows and role/capability checks. Validate that the shared approach works with the actual miniOrange edition on Rooted Psyche, as well as WooCommerce login and role behavior on Dank Mushrooms. Select a shared implementation mechanism only after confirming constraints; do not presume a paid miniOrange feature exists.

**Implementation sequence:** shared integration contract and dual-site regression tests → Rooted Psyche board director SSO pilot → Rooted Psyche revocation and existing-session acceptance → optional Dank Mushrooms staff/developer SSO on a non-production or controlled installation, with *negative tests proving WooCommerce customer login/checkout never touches authentik*. No live Dank Mushrooms storefront authentication change is authorized by the initial Rooted Psyche work.

Track first site in [#146](https://github.com/RayzorDuff/RootedOps/issues/146) and overarching identity in [#139](https://github.com/RayzorDuff/RootedOps/issues/139). Continue changes in existing documentation PR #141.


### Read-only production inventory before WordPress SSO deployment

**Code PR:** `feature/wordpress-auth-inventory-146` introduces `scripts/wordpress_auth_inventory.php` (CLI-only; static lint checked). It reports **active plugin names/versions, role counts and board-director user IDs, SSO-related option *names only*, board-page existence, site hostname, and WooCommerce presence**. It deliberately does not export wp_options **values**, emails, access tokens, or passwords. The repository contains Rooted Psyche WordPress `wordpress:6.8.3-php8.3-apache` and separate Dank WordPress `wordpress:7.1.4-php8.3-apache` in distinct Compose files/DB volumes. The Rooted Psyche board-library plugin currently checks *local* WP `administrator` or `board_director` role on each shortcode and download request; WordPress role projection and revocation thus need a real implementation, not just authentik login.

**No live site inventory has been executed by this PR.** The active miniOrange edition/configuration and board Members role assignments must be confirmed using the following read-only runtime probe before picking a role mapper or registering OAuth callback URIs.

After the **code** PR is reviewed/merged and pulled to the host, run from `~/RootedOps`:

```bash
set -euo pipefail
cd ~/RootedOps
# Read-only runtime report: no container recreation, plugin activation or database mutation.
sudo docker cp scripts/wordpress_auth_inventory.php \
  rootedpsyche-wordpress:/tmp/rootedops-wordpress-auth-inventory.php
sudo docker exec rootedpsyche-wordpress \
  php /tmp/rootedops-wordpress-auth-inventory.php
# Run the same non-invasive probe on the independently deployed WooCommerce stack:
sudo docker cp scripts/wordpress_auth_inventory.php \
  dank-wordpress:/tmp/rootedops-wordpress-auth-inventory.php
sudo docker exec dank-wordpress \
  php /tmp/rootedops-wordpress-auth-inventory.php
```

The running containers may have different names (check `sudo docker ps --format '{{.Names}}'`); use the *actual* names rather than modifying Compose. **Treat output as internal operational information** even though it excludes values. Do not paste live OAuth client secrets, login-option values, WordPress password hashes, database exports or full user profile data into an issue.

Inventory interpretation checklist:
- Rooted Psyche: exact miniOrange plugin basename/version, its SSO configuration *capabilities* (not secrets), active Members plugin/role and board library, existing WP board user IDs, site-specific login/logout.
- Dank: WooCommerce and customer registration/My Account/checkout, customer webhook plugin, any staff login plugins, existing admin users, protected ERPNext customer linking.
- Both: administrator break-glass, any SSO modules requiring a paid license for group→role mapping or user linking, and whether there is a trustworthy session-revocation mechanism.
- Design a **reusable** integration with independently configured OIDC applications/clients per WordPress site. Initial code/rollout must change only Rooted Psyche; no automatic redirect of Dank customers to authentik.

Implementation gate: do **not** cut over login, enable a group/role synchronizer, change `board_director` memberships, or remove miniOrange until runtime plugin inventory and a staged login + role-removal test have established continuity for existing board users, denial to non-board Spiritual Practitioners, and revocation for already-authenticated board sessions. Track in [issue #146](https://github.com/RayzorDuff/RootedOps/issues/146).


### Actual Rooted Psyche production inventory — 2026-11-27

Read-only `scripts/wordpress_auth_inventory.php` run succeeded on the real Docker Compose WordPress service (`docker-rootedpsyche-wordpress-1`; use Compose `ps -q rootedpsyche-wordpress`, **not** assumed container name `rootedpsyche-wordpress`). Results:
- URL host `rootedpsyche.org`, WordPress **7.1.5** (runtime; base Docker image is pinned to `wordpress:6.8.3-php8.3-apache`), single site, **WooCommerce inactive**.
- Active plugins: `members` **3.3.1**, `miniorange-login-openid` **7.9.1** (*Social Login, Social Sharing*, not miniOrange's separate generic OAuth/OIDC SSO product), `rootedpsyche-board-library` **0.3.0**, `fluent-smtp` **2.4.1**, `bookworks-original-html` **0.1.0**, `givebutter` **1.0.5**, `wp-file-manager` **8.0.6**.
- Four existing `board_director` WordPress users, IDs **2, 4, 5, 6**; one administrator, no members of the other counted core roles. Board page `/board/` is published (ID **60**). Board library's `rp_board_library_authorized()` function present.
- Runtime option *names* include `mo_openid_login_role_mapping` but **option existence does not prove a working authentik group-mapping function**, nor that existing users can be matched to a stable OIDC subject. No secret values were inspected.

**Implementation consequence:** The current miniOrange product is social-login oriented; do not reconfigure or uninstall it as if it were the generic OIDC miniOrange plugin. Authentik's [official WordPress integration](https://integrations.goauthentik.io/platforms/wordpress/) uses the open-source [OpenID Connect Generic Client](https://wordpress.org/plugins/daggerhart-openid-connect-generic/). Evaluate adding it as an **optional parallel login** first, without automatic role elevation or new-user creation, then layer reusable, per-site-role mapping and existing-session revocation on top. Account linking to WordPress IDs 2/4/5/6 must be explicitly approved before production login. Authenticate vs authorize separately: existing WordPress role checks remain effective, and a stale WordPress role must not grant board access after authentik revocation.

**No live WordPress settings or roles have been changed by the inventory.** Dank Mushrooms production plugin/user inventory is still required; keep WooCommerce authentication and ERPNext customer integration untouched. Track implementation progress in [#146](https://github.com/RayzorDuff/RootedOps/issues/146) and code pilot in draft [PR #147](https://github.com/RayzorDuff/RootedOps/pull/147).


### Actual Dank Mushrooms WordPress production inventory — 2026-11-27

Read-only `scripts/wordpress_auth_inventory.php` successfully ran on the Dank WordPress Compose service (container actual name `dank-store-test-dank-wordpress-1`, selected through `docker compose ... ps -q dank-wordpress`). The site reports hostname **`dankmushrooms.net`**, WordPress **7.1.5**, **WooCommerce 11.2.1 active**, single-site (not multisite). The original Compose base image tag is `wordpress:7.1.4-php8.3-apache`; runtime reported version supersedes that as observed fact.

Roles: **one administrator**, **ten customers**, and zero board directors, shop managers, editors, authors, contributors or subscribers. `/my-account/` page ID **10** and `/checkout/` page ID **9** are published. No WordPress OAuth or miniOrange login plugin is currently active. Active plugins include Clover Payments 2.3.2, USPS live rates 3.6.3, Shipping Zones by Drawing for WooCommerce 3.5.0, WooCommerce Shipping 2.5.1 and FluentSMTP 2.4.1. The inventory records only regular active plugins and does **not** enumerate MU plugins; RootedOps' Dank Compose separately mounts the customer-webhook and fulfillment MU plugins.

**Design conclusion:** WordPress SSO needs **per-site opt-in configuration** with centralized authentik identities only for approved organizational users. Initial deployment is Rooted Psyche only. A future Dank developer/administrative SSO integration must leave WooCommerce customer login, registration, My Account, checkout, password recovery, roles, order ownership, ERPNext customer links and commerce webhooks unchanged. Do not install/activate OIDC on Dank to complete the Rooted Psyche pilot.

**Next gate:** select/verify current patched generic OpenID Connect Client plugin release, run a controlled Rooted Psyche existing-user sign-in test, and explicitly map authentik board groups to the existing WordPress user IDs and `board_director` role without disturbing the separate WP administrator. **A successful login alone does not establish board-member revocation for existing sessions.** Track in #146.

### Board communication pending WordPress SSO acceptance

The privately addressed board-member notice (new Google Workspace email, optional Gmail and other mailbox access via MailFlow, new WordPress board login, optional authentik Connected services linking) is drafted using placeholders in [ROOTEDPSYCHE-BOARD-IDENTITY-ONBOARDING.md](ROOTEDPSYCHE-BOARD-IDENTITY-ONBOARDING.md). **Do not send** until #146 acceptance verifies actual WordPress login and group-based authorization and user identity linking. Public repository documentation must not store real names paired with email addresses, personal Gmail/secondary addresses, temporary Google Workspace passwords, or real identity-link mappings. Existing historical Git commits and issue comments are not made private by editing the current PR branch.


## Rooted Psyche WordPress authentik integration — code pilot 2026-11-27

**In implementation, not live:** draft code PR #147 (`feature/wordpress-auth-inventory-146`) now includes `wordpress/mu-plugins/rootedops-wordpress-authentik.php` and a **single opt-in filter** in the Rooted Psyche board-library plugin. It is **disabled by default** and changes no WordPress logins, board privileges or WooCommerce flows merely by deploying the files. The external [OpenID Connect Generic Client](https://wordpress.org/plugins/daggerhart-openid-connect-generic/) is a separate third-party plugin, **not vendored or installed** by #147. Before activating, validate its current published version and follow its [WordPress / authentik integration](https://integrations.goauthentik.io/services/wordpress/) guide.

### What the opt-in pilot does

- Enabled only on Rooted Psyche when **both** `ROOTEDOPS_AUTHENTIK_WP_PILOT === true` and `ROOTEDOPS_AUTHENTIK_WP_SITE === 'rootedpsyche'` are configured in WordPress's trusted configuration. Nothing in PR #147 sets these flags.
- Uses generic OIDC client hooks to **deny automatic user creation**, and accepts a login **only** if the signed OIDC claims contain an explicitly pre-linked `sub` mapping to one unique WP user via `rootedops_authentik_subject` usermeta, a verified email claim, and an exact match to that same WP user's existing email address. Never grants admin or Woo customer privileges. This stringent email match is a **pilot guard**, not the final solution for users with differing canonical authentik/WordPress emails.
- Only after the OIDC plugin has authenticated an existing user, verifies that the WP user ID matches the pre-linked `sub` before projecting `rootedpsyche-board-directors` claim into the existing WP `board_director` role. It records short-lived authorization metadata. Never sets the WP `administrator` role.
- Adds `rootedpsyche_board_library_authorized` filter to all protected board library downloads/listings; when pilot enabled, non-admin board access requires a current (<=300 seconds) claim snapshot. The `/board/` page tree also checks freshness in `template_redirect` for logged-in users. **A five-minute expiry is a temporary security pilot**: it fails closed, but users must reauthenticate or refresh authorization after expiry, and more permanent session refresh/revocation must be implemented and validated before general board rollout. The board page HTTP cache must remain disabled; test all board routes and nonpage endpoints.
- Admin local login remains available; with the pilot enabled, WordPress `administrator` remains an explicit recoverable exception to the board guard. The existing miniOrange social login remains intact until the new route passes acceptance.

### Before enabling (do not skip)

1. Snapshot and verify WordPress database and HTML-volume recovery. Inventory live four existing board-director WP IDs (2,4,5,6) and ensure the new test identity resolves to the **intended existing** WordPress account. The authentik Workspace source link and canonical verified-email marker must be reconciled first. Do not paste the resulting identity/email mappings into public Git.
2. In authentik, create organizational group `rootedpsyche-board-directors`, and assign the approved **test identity**. Do not put ordinary Workspace mailbox holders or all practitioners into this group automatically.
3. Create separate Authentik **OAuth2/OpenID Provider + Application** named `Rooted Psyche WordPress`, slug `rootedpsyche-wordpress`, issuer-per-provider as appropriate. Strict redirect URI for the generic WP client defaults to `https://rootedpsyche.org/wp-admin/admin-ajax.php?action=openid-connect-authorize` or its configured alternate `https://rootedpsyche.org/openid-connect-authorize`; confirm the selected plugin's actual **displayed callback**, then register *only that exact URI*. The plugin needs login, token, userinfo, JWKS and issuer endpoints from the authentik OIDC discovery document. Use `openid email profile` with a trusted `groups` claim mapping (standard provider profile scope only if verified to emit the expected group field). Keep client secret in private WordPress settings or `.env`, never Git.
4. Install/activate the generic OIDC plugin **with login type button**, not automatic redirect. Keep miniOrange and independent local WordPress administrator login. Disable generic OIDC automatic account creation and automatic email-based account linking in plugin options. Do not assume its plugins share the same behavior or options.
5. Independently reconcile desired authentik `sub` and exact WP ID, without email auto-merging. The initial pilot **requires the authenticating OIDC email to equal that existing WP user's email**. If they differ, **stop**—do not change the WP user's email or attempt administrative account takeover merely to make the test pass; revise the account selection integration design.
6. Only after OIDC credentials and stable account link are tested, stage the MU adapter **and** board library filter, run PHP lint/tests, set both feature flags, and test with separate administrator recovery browser. No mass group mapping or directory sync in this pilot.

### Required acceptance before activating for other directors

- Positive: authorized test board director authenticates via authentik to **same WordPress user ID**, board page and board-library access. No duplicate user creation.
- Negative: authenticated non-board Spiritual Practitioner is **denied** board page and direct protected file downloads; unrelated Workspace identity cannot obtain `board_director` just from domain.
- Revocation: remove group in authentik, demonstrate no continued board access from existing WordPress sessions beyond the tested short expiration bound **or** immediate group sync; note the current pilot TTL requires re-login and may be operationally unsuitable. A new SSO login without board group removes the local WP `board_director` role.
- WordPress administrator local recovery works; old miniOrange login works until deliberately retired; no change to MailFlow or Dank WooCommerce customer login.

**Status:** The repo can stage these optional code paths, but *does not contain live authentik WP provider credentials or a proven stable subject-to-WP account association*. Those require controlled operator configuration and browser acceptance before the pilot is actually enabled. Track #146; code PR #147, this documentation in existing docs PR #141 only.
