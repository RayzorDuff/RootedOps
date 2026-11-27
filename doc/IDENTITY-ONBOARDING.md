# RootedOps identity onboarding — administrator and user guides

> **CURRENT DECISION (2026-11-27):** The Google OAuth consolidation discussions in this document are **historical proposals, not an approved migration**. Keep all three existing Google login choices and their verified working account links unchanged. The next project is **Rooted Psyche WordPress SSO**, with **authentik-managed organizational roles as the authority for board access**. See [IDENTITY.md — Architecture decision](IDENTITY.md#architecture-decision--organizational-role-authorization-2026-11-27). Do not change the MailFlow authentication paths while integrating WordPress.

**Status:** Operationally verified for one person (`ray@edanks.com`, 2026-11-26); further onboarding is manual/controlled. Tracks [RootedOps #139](https://github.com/RayzorDuff/RootedOps/issues/139). Do not treat proposed automation below as already implemented.

## What is provisioned, and what is not

Four separate objects are involved:

1. **RootedOps person / authentik user:** `RayDanks` is an *internal* user, linked to the `google-edanks` Google source. `akadmin` remains a *separate* local recovery administrator; using the same contact email does not merge them.
2. **Application entitlement:** authorized access to the authentik MailFlow application. An authentik account and Google login alone should never imply board, staff, or MailFlow access.
3. **Application-local MailFlow user:** existing `ray@edanks.com`; a SSO link connects its UUID to the trusted authentik issuer + subject. MailFlow identity may have a different username from its mailbox addresses.
4. **Mailbox connection:** independently-authorized Gmail/Workspace OAuth or IMAP/SMTP credentials. Google OAuth *identity* sign-in never authorizes reading Gmail. No mailbox is automatically provisioned by the current SSO setup.

A mail user can have many personally-connected mailboxes; no cross-user sharing is implied. Organization-owned mailboxes, invitation delivery email, and personal recovery contact are separate.

## Administrator procedure — reproduce the first working MailFlow login

**Prerequisites:** authentik 2026.8.7 running at `https://auth.danks.store`, MailFlow 4.5.1 running at `https://mail.danks.store`, both HTTPS and backups validated. Keep existing admin sessions active until end-to-end login works. Never paste OAuth client secrets into tickets or Git.

### A. Configure authentik Google Workspace identity source (once)

1. In the `edanks.com` Google Cloud project, create an identity-only **Internal** Web OAuth client for authentik. Use Google callback `https://auth.danks.store/source/oauth/callback/google-edanks/` and only identity scopes (`openid`, `email`, `profile`). Do not reuse the restricted Gmail mailbox OAuth client.
2. In authentik Admin → Directory → Federation and Social login, create Google OAuth Source, name `Google Workspace — edanks.com`, slug `google-edanks`, and insert the Google client credentials. Ensure source is selected by the default authentication identification stage.
3. Test private-window Google sign-in as `ray@edanks.com`. Initially authentik created `RayDanks` as **external**; direct authentik dashboard showed “Interface can only be accessed by internal users.” Changing *only* this user's type to **internal** allowed direct dashboard access. External users can still sign in to applications; do **not** globally make all social users internal.
4. Maintain a separate `akadmin` with local credentials and MFA. Do not automatically merge `akadmin` with the personal Google identity.

### B. Configure authentik OIDC application for MailFlow (once)

1. Authentik Admin → Applications → Applications → New Application with OAuth2/OIDC confidential provider. Application slug `mailflow`. Use exact callback `https://mail.danks.store/auth/oidc/rootedops/callback`. Keep `openid` and `profile` mappings.
2. The issuer is `https://auth.danks.store/application/o/mailflow/`. Check discovery:
   ```bash
   curl -fsS https://auth.danks.store/application/o/mailflow/.well-known/openid-configuration | python3 -m json.tool
   ```
   It must report that issuer and the HTTPS token/JWKS endpoints. Save client ID and secret securely for MailFlow's SSO provider (not in Git).
3. **Verified email mapping required by MailFlow:** authentik 2025.10+ defaults to `email_verified: false`. In authentik Customization → Property Mappings create a **Scope Mapping** named `RootedOps - Verified Email` with scope name `email` and expression:
   ```python
   email = request.user.email
   verified_address = request.user.attributes.get("email_verified_address")
   return {
       "email": email,
       "email_verified": bool(email and verified_address == email),
   }
   ```
   In MailFlow's authentik OAuth2/OIDC provider, replace (not supplement) the built-in `OpenID 'email'` mapping with this custom `email` mapping. Keep `openid` and `profile` mappings. **This mapping is only as trustworthy as the process populating verified attributes.**
4. For the **already authenticated, individually verified pilot user**, authentik Directory → Users → `RayDanks` → Edit → Advanced settings → Attributes was set to the YAML below, preserving existing source list:
   ```yaml
   settings:
     locale: ""
   email_verified_address: "ray@edanks.com"
   goauthentik.io/user/sources:
     - Google Workspace — edanks.com
   ```
   **Critical:** `email_verified_address` must be **top-level**, *not* indented under `settings`. The incorrect indentation caused MailFlow's “Your email address must be verified with this SSO provider” error. Do **not** set this attribute by guess or just because an email is typed into a user record. For everyone else, use a verified upstream claim or an actual email verification workflow (design below).

### C. Configure MailFlow OIDC provider and explicitly link the user

1. Sign into the **existing local MailFlow administrator** at `https://mail.danks.store`. In Settings → Administration → Single Sign-On, create provider:
   - Name `RootedOps Identity`, slug `rootedops`.
   - Issuer `https://auth.danks.store/application/o/mailflow/`, authentik client ID/secret, `openid email profile`.
   - Provisioning **Match existing** (MailFlow's `login_existing_only`), **Require verified email** enabled, **Allow insecure** disabled; do not configure untested admin-group mappings, RP logout, or provider-MFA exemption.
   - Keep local login available as fallback. **Never enable open SSO user provisioning by default.**
2. While still authenticated as the existing MailFlow user, open Settings → Security → **Linked SSO accounts**, choose RootedOps Identity, confirm reauthentication, and complete Google → authentik. Verify the linked identity displays the intended email and provider. **Do not begin with the SSO button on MailFlow's login page when an unlinked existing user must be preserved.**
3. In an independent incognito browser, open `https://mail.danks.store/login` → **Sign in with RootedOps Identity** → authentik → Google Workspace. Verify the SAME MailFlow username, original mailboxes, account settings and permissions, with no duplicate user. Retest local password recovery.

### D. Safe acceptance / troubleshooting

- `email_verified` failure: check **(1)** top-level `email_verified_address` on authentik user; **(2)** custom `email` scope mapping expression; **(3)** exactly one selected `email` scope mapping on the authentik application; **(4)** latest Google-authenticated user and email; **(5)** MailFlow Require verified email remains on. Old MailFlow `user_identities.email_verified=false` rows may reflect initial linking and need not be changed manually. **Do not UPDATE that field in PostgreSQL** to bypass verification.
- Distinguish authorization (authentik user/provider works), dashboard access (`Internal` vs `External` user), MailFlow linking (Security), and Gmail mailbox access (separate).
- Confirm OIDC issuer via read-only discovery, never print `client_secret`, OAuth authorization codes, access tokens, or session cookies. Authentik request logs may include codes/state — **do not publish raw logs**.
- Read-only MailFlow identity linkage diagnostic:
  ```bash
  sudo docker exec mailflow-postgres psql -U mailflow -d mailflow -c "
    SELECT u.username, p.name AS provider, i.email AS linked_email,
           i.email_verified, i.last_used_at
      FROM user_identities i
      JOIN users u ON u.id=i.user_id
      JOIN oidc_providers p ON p.id=i.provider_id
     WHERE p.slug='rootedops';"
  ```
  This inspects stored link history, not necessarily what the **current** OIDC token says. Never mutate MailFlow's linked identity tables as a shortcut.

## Administrator procedure — onboard an approved additional user (CURRENT manual path)

1. Record **person**, intended **organization**, **roles/app grants**, *personal invitation delivery address*, *approved organizational address* and whether the MailFlow user/mailbox already exists. Use a unique stable person identifier and collect approval; do not auto-assign board roles by `@rootedpsyche.org` suffix.
2. Ensure the authentik person exists and confirm their desired external source is **linked to that person**, with unique provider issuer/subject. Avoid automatic merges based only on email. Invite/authorize the user before exposing an application. Set app-access policies/groups; these are **still future work** for the generalized RootedOps identity model.
3. Establish and store verification of the user's **current** email by trusted upstream `email_verified=true` claim **or** authentik's email-confirmation stage. If needed, the verified-address attribute must be **top-level**, and it must be cleared or invalidated on email change. Never populate it from an unverified invitation delivery address alone. Do not blindly copy the pilot's user-attribute YAML.
4. If the MailFlow user already exists, have them sign in locally first and **link** RootedOps Identity under Settings → Security. If no user exists, use MailFlow's supported admin **invitation** path to create the user, then link the OIDC identity. Ensure MailFlow registration is closed to public users.
5. The user performs a private-window SSO login; admin confirms identity maps to only the intended MailFlow UUID, its own mailboxes and correct app permissions. Verify their app and organization memberships separately. Organization mailbox auto-attachment is **not implemented**.

**Rooted Psyche:** The `rootedpsyche.org` Google Workspace OAuth source and a personal Gmail External identity-only OAuth source are not yet configured for all users. WordPress's existing miniOrange Google SSO and `board_director` role mappings must remain in force until each board user is explicitly linked and tested; an authentik user login must not silently mint a WordPress board account.

**Dank Mushrooms:** Mail hosting and one-managed-password policy are unresolved. Never imply that successful SSO creates a `@dankmushrooms.net` mailbox or proves ownership of an IMAP account.

## User-facing guide — first-time and returning MailFlow users

**Invitation:** The administrator sends an invitation to the approved contact email (which may be **different** from the company mailbox). The invitation identifies the intended RootedOps/organizational account. Only accept an invitation intended for you. Authenticate using the provider specified (for example Google Workspace) and do not create an arbitrary second account when an approved account already exists.

**First visit if the MailFlow user already exists:**

1. Open `https://mail.danks.store` and sign in using your **current MailFlow username/password**.
2. Go to **Settings → Security → Linked SSO accounts**, select **RootedOps Identity**, and follow the confirmation/reauthentication and Google/authentik sign-in screens.
3. Return to Security and verify the correct provider and identity are shown. **Do not unlink existing identities.**
4. Sign out. Open a new private window and select **Sign in with RootedOps Identity**.
5. Sign in with your approved Google/other linked authentik identity. You should see the same MailFlow account and any previously connected mailboxes.

**First visit if MailFlow account is not yet created:** use the administrator-issued MailFlow invitation to create your account, then complete the account-linking steps above. **No universal SSO-only invite activation or automatic mailbox attachment has been deployed yet.** If you cannot access the local invitation or have a provider-linking error, contact the administrator rather than enrolling a second user.

**Returning visit:** `https://mail.danks.store/login` → **Sign in with RootedOps Identity** → approved Google identity. The authentik screen may offer a username field and an external Google sign-in icon; use your approved provider. Your work/personal mailboxes are separate connections under your MailFlow user, not alternative RootedOps identities.

**Mailboxes:** You may add personally owned email accounts under MailFlow's account settings; OAuth consent to read Gmail is a separate, more sensitive permission than sign-in via Google. An administrator must separately authorize and provision organizational mailboxes. Never give a personal mailbox password to an organization administrator.

## Automation blueprint — design to implement and test (NOT DEPLOYED)

The goal is one controlled **admin invitation** + one verified **user acceptance**, not a sequence of per-user authentik/MailFlow manual mutations.

1. **Pre-provision** immutable RootedOps person, organization membership, app entitlement, and target authentik user (prefer inactive/pending until validated). Invitation may be delivered to an external personal address. Enforce one-use, time-limited, audited tokens and explicit organization admin approval.
2. **Federate trusted identity**: use authentik OAuth Source User Property Mapping to read `info.get("email")` and `info.get("email_verified")`. Only when the trusted upstream identity supplies a verified true claim for the exact current email should automation set `attributes.email_verified_address`; otherwise require a confirmation email stage. Bind to specific approved source(s), not all social/OAuth providers. Source mappings can run on enrollment/login, but do NOT start auto-claiming existing accounts by email or overwriting a verified marker for other sources without design review.
   - **Candidate expression for a tested Google-OIDC source**, not yet deployed (must verify actual `info` claims and source mapping merge behavior in staging):
     ```python
     upstream_email = info.get("email")
     upstream_verified = info.get("email_verified") is True
     return {
         "attributes": {
             "email_verified_address": upstream_email if upstream_verified else None
         }
     }
     ```
     For a production implementation, handle missing/unverified changes and revocation in a way that **cannot retain stale verification**. Authentik's property mapping docs note `None` can discard an attribute during merge; test this explicitly. Bind only after confirming that the source issuer and subject are already linked to the approved person.
3. **MailFlow user provisioning**: prefer MailFlow's supported admin invite or other supported user API (validate current version). Link the authentik OIDC identity to the **existing** MailFlow user through its first-party verified linking flow. Do not insert encrypted tokens, passwords or identity links directly into PostgreSQL. For new SSO-only invited users, design an application-supported initial linking/bootstrap mechanism rather than opening public auto-provisioning.
4. **Organization mailbox**: for Rooted Psyche, require the person's Gmail consent or a documented authorized delegation; for Dank Mushrooms, wait for the chosen mail provider and secure API/secret design. Neither can be inferred from the authentik session.
5. **Verification gates**: approved invitation + issuer/subject, exact verified email, correct group/app entitlement, correct MailFlow user UUID, separate per-mailbox authorization, sign-in acceptance, deprovision/rollback, backup/restore, audit, MFA and no extra app roles. Manual fallback when identity linking conflicts.
6. **Idempotence and reconciliation**: provisioning calls may succeed partially. Persist durable internal IDs, never duplicate accounts on retry, and make partially failed invitations visible for operator repair. Track application grants separately from organization membership to support external collaborators and multiple companies.

### Acceptance scenarios before rollout

- Invite existing MailFlow user with Google Workspace identity, preserve MailFlow UUID/mailboxes and require no per-user manual claim configuration.
- Invite a board member via personal email; verify both personal Google and Workspace identities link to one authentik user, while WordPress `board_director` access remains explicitly approved.
- Reject unverified/changed email, wrong OAuth issuer/subject, expired/replayed invite, same email on different identities, and unauthorized organization crossing.
- An approved external user only sees applications granted to them; no cross-user mailbox exposure.
- Provision/restore/offboard without deleting personally connected mailboxes or breaking the `akadmin` emergency account.

## External references

- [authentik: Verify email addresses (OIDC)](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/verify-email-address/)
- [authentik: OAuth source property mappings](https://docs.goauthentik.io/users-sources/sources/protocols/oauth/)
- [authentik: Source property mapping merge semantics](https://docs.goauthentik.io/users-sources/sources/property-mappings/)
- [MailFlow: upstream source repository](https://github.com/maathimself/mailflow)

## Current rollout: SSO-only MailFlow accounts

For the approved group-gated Open provisioning path and domain-wide trusted-Workspace admission policy, see [IDENTITY-MAILFLOW-SSO-PROVISIONING.md](IDENTITY-MAILFLOW-SSO-PROVISIONING.md). The earlier password-based MailFlow invitation steps above are historical/manual fallback, **not the desired production path**. Existing Cormac account was invited as username `cormac`, renamed safely to `cormac@edanks.com`, then SSO linked and accepted with verified-email attribute automatically populated. New Open-provisioned MailFlow users should have no local password.

## Second authentication method for one person — personal Google (planned first test)

**Goal:** authenticate as the already established authentik user `RayDanks` with either `ray@edanks.com` (Internal Workspace Google source `google-edanks`) or `raymonddanks@gmail.com` (new External personal Google source `google-personal`) and reach the *same existing MailFlow account*. Source linking is authentik identity management, not a new MailFlow identity or mailbox.

1. Create a **separate Google Cloud project** with External OAuth audience and an identity-only Web OAuth client (`openid email profile`). Redirect `https://auth.danks.store/source/oauth/callback/google-personal/`. Do not change the existing Internal Workspace client or request restricted Gmail mailbox scopes.
2. Create an authentik Google OAuth Source named `Google — Personal Accounts`, slug `google-personal`, using this new client. Use **identifier/source identity matching**, never auto-link accounts based on a matching email or username. Do not assign the source the `google-edanks` verified-email mapping and do not automatically add personal Google users to `mailflow-users`. Add the source to the login page's identification stage.
3. **Critical:** First sign into authentik as the EXISTING `RayDanks` via edanks.com; in **User Settings → Connected services** choose **Connect** on `google-personal`, and explicitly choose `raymonddanks@gmail.com` at Google's account chooser. Do **not** use the unauthenticated login-page Google button for first linking, which can enroll a duplicate authentik user.
4. Confirm under the same `RayDanks` account that **both** external Google sources are linked. Confirm no second authentik Ray user exists. Verify current authentik user email remains `ray@edanks.com`, and that the trusted `email_verified_address` still corresponds to the OIDC `email` claim emitted by the verified-email scope mapping. A personal-source user mapping might update the canonical email; if so **stop before attempting MailFlow**, restore via admin only after verifying the source mapping behavior and adjust the personal source to preserve canonical identity fields.
5. Keep `RayDanks` in `mailflow-users`. This makes application access independent of which Google identity was used. **Do not grant MailFlow access to all users of `google-personal`**. The automatic Workspace source-path expression covers independently enrolled edanks.com users; personal Google is admitted only through explicit existing group membership.
6. Test a fresh private-window **authentik** login using personal Google first. Inspect the resulting authentik user ID/username before following through to MailFlow. Then try `https://mail.danks.store/login` → RootedOps Identity → personal Google; require the same MailFlow user `ray@edanks.com`, same mailboxes, and no duplicate record. The MailFlow OIDC issuer+subject remains the stable authentik person for both Google methods.
7. Test the original edanks.com login again and verify it remains functional. Preserve `akadmin` break-glass local login.

**Security:** Personal Google identity login does not authorize Gmail mailbox access. Do not copy personal Gmail address into `attributes.email_verified_address` if the authentik canonical email remains `ray@edanks.com`; OIDC verified email must accurately describe the emitted email claim. If a login unexpectedly creates another authentik user or changes `RayDanks` email, stop, avoid merging or deleting records blindly, and inspect source links and mappings.

**Future admission test:** After this explicit linked-user scenario is proven, use a separate *unapproved* personal Google identity to confirm MailFlow application's Workspace-source policy does not grant access by mere email/name, and that `mailflow-users` remains the explicit admission mechanism. This negative test must precede general personal-source rollout.

## Validated two-upstream-identities → one authentik person → one MailFlow account (2026-11-26)

**Operator-verified:** Existing authentik internal user `RayDanks` signed in through `google-edanks`, used **User interface → Settings → Connected services → Connect** to attach `google-personal` using `raymonddanks@gmail.com`, and confirmed that the authentik canonical email remained `ray@edanks.com`. Logging into MailFlow after using personal Google returned the **same existing** MailFlow account as the Workspace identity. This is successful account linking, not a second MailFlow user or permission grant.

Existing `google-personal` source settings: slug `google-personal`, user/group matching **Link users on unique identifier**, no Workspace-specific user property mapping selected, standard source authentication/enrollment flows. Google Cloud project is **External**, identity-only OAuth, web callback `https://auth.danks.store/source/oauth/callback/google-personal/`. Do not confuse this with Gmail mailbox OAuth.

### Login-screen usability: distinguish Google sources

By default authentik's Identification stage shows OAuth sources as icons, causing two identical Google `G` icons. There is no need to create custom icons, modify CSS, or use a commercial tier just to show names:

1. Authentik Admin → **Flows and Stages → Stages** → edit the **Identification stage used by** `default-authentication-flow` (typically `default-authentication-identification`).
2. Locate **Source settings → Show source labels** and enable it. Verify it applies to all selected OAuth sources. This displays the distinct source names alongside their otherwise identical Google icons.
3. Optionally edit each source at **Directory → Federation and Social login** and toggle **Promoted** to display each as a prominent full-width button rather than a small icon; use if login looks better with several sources. This is separate from labels and is available in authentik 2026.8.
4. Set source **display names** (not slugs): `Google — edanks.com Workspace`, `Google — Personal Accounts`, and later `Google — rootedpsyche.org Workspace`. Preserve slugs `google-edanks` and `google-personal`, OAuth credentials, source IDs, mapping and source links.
5. Test private-window MailFlow-initiated login. Choose each named source separately and verify both lead to the same `RayDanks` identity and `ray@edanks.com` MailFlow account. In future, confirm personal Google users without explicit group approval remain denied; the automatic edanks Workspace admission policy must not apply to personal Google source accounts.

References: [authentik Identification stage — Show source labels](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/identification/), [authentik OAuth source fields and Promoted](https://api.goauthentik.io/reference/sources-oauth-retrieve/).


## Rooted Psyche Workspace rollout — next deployment (planned, 2026-11-26)

**Goal:** Add `rootedpsyche.org` as a separate Google **Internal** OAuth source and grant all verified, source-enrolled Rooted Psyche Workspace users automatic MailFlow access. Existing authentik person `RayDanks` must later link their `rootedpsyche.org` source to the same identity as `ray@edanks.com` and personal Gmail, preserving the MailFlow subject, canonical email, mailboxes and roles. WordPress OIDC is a separate acceptance stage; do not change current WordPress miniOrange/board roles now.

### Google Cloud and authentik source (admin)

1. In the **rootedpsyche.org Google Workspace** Google Cloud organization/project, create a dedicated Google Auth Platform OAuth application with **Internal** audience, name `RootedOps Identity — Rooted Psyche`, identity scopes `openid email profile`; create confidential Web OAuth client with exact redirect `https://auth.danks.store/source/oauth/callback/google-rootedpsyche/`. No Gmail mailbox scopes, JS origin or paid authentik Workspace provisioning connector.
2. In authentik Admin → Directory → Federation and Social login, create **Google OAuth Source** named `Google — rootedpsyche.org Workspace`, slug `google-rootedpsyche`, use that client ID/secret; user/group matching **Link users on unique identifier**, default source authentication and enrollment flows, no email-based automatic merge. Add source to the existing default identification stage (Show Source Labels already on).
3. Create a new **OAuth Source User Property Mapping** named `RootedOps - Google Workspace rootedpsyche.org verified email` with:
   ```python
   email = info.get("email")
   email = email.strip().lower() if isinstance(email, str) else ""
   verified = (
       info.get("verified_email") is True
       or info.get("email_verified") is True
   )
   return {
       "attributes": {
           "email_verified_address": (
               email if verified and email.endswith("@rootedpsyche.org") else ""
           )
       }
   }
   ```
   Attach this mapping to **only** `google-rootedpsyche`; do not attach the existing `google-edanks` mapping. This is the new-user pilot mapping, not yet multi-identity-safe.
4. In authentik Admin → Customization → Policies → Expression Policy, create `MailFlow - Verified rootedpsyche Workspace`:
   ```python
   user = request.user
   email = (user.email or "").strip().lower()
   verified = (user.attributes.get("email_verified_address") or "").strip().lower()
   return (
       user.is_active
       and email.endswith("@rootedpsyche.org")
       and email == verified
       and (user.path or "") == "goauthentik.io/sources/google-rootedpsyche"
   )
   ```
   Bind **enabled, non-negated** to **Applications → Applications → MailFlow → Policy / Group / User Bindings**. Retain `mailflow-users` and the verified edanks Workspace expression; Application **Policy engine mode = Any**. This source-specific rule is safe only so long as the Google Cloud OAuth client remains Internal to the Rooted Psyche Workspace and user paths/verified-email attributes are admin-controlled. It does not grant WordPress board access.
5. Keep MailFlow OIDC **Open** provisioning with **Require verified email ON**, local public registration OFF, no automatic SSO-admin group claims. Test a **new, independently approved Rooted Psyche Workspace user** in a private browser; first authentik enrollment should assign source path `goauthentik.io/sources/google-rootedpsyche` and top-level verified marker, application policy allows access, MailFlow creates `username=user@rootedpsyche.org` with `is_admin=f` and `password_hash=NULL`. Confirm no mailboxes are attached automatically. Retest Ray, Cormac and Ethan; no duplicate MailFlow users.
6. Preserve a negative test for independently enrolled `google-personal` Gmail user not in `mailflow-users` (should authenticate to authentik but be denied MailFlow). This was deferred in the previous pilot. Do not test nonmembers by removing the existing Ray/Cormac bindings.

### Multi-source linking caveat: RayDanks

**Do not immediately link `admin@rootedpsyche.org` (or other Rooted Psyche login) into `RayDanks` with the simple rootpsy marker mapping above.** Authentik OAuth source user mappings can update attributes on an existing linked user. The new source mapping could overwrite `RayDanks.attributes.email_verified_address` with `admin@rootedpsyche.org`, even though the OIDC provider emits the **canonical** `ray@edanks.com`. This will make the MailFlow verified-email mapping return false, breaking both login methods. Also, the source-path access expression is only meant for separately enrolled Workspace-native users; linked RayDanks retains access from `mailflow-users`.

Before RayDanks connects a third source, implement/test a **canonical-email-aware** source verified marker rule or a per-source verified-email record plus OIDC mapping that verifies the *currently emitted* canonical email without clobbering another source's marker. Test with a nonproduction linked identity, retaining `RayDanks`'s existing subject, group and mailboxes, before repeating **User Settings → Connected services → Connect**. Do not merge identities by email and do not modify MailFlow user identities directly.

### Next: WordPress

Once new Rooted Psyche MailFlow accounts and RayDanks multi-source linking are separately proven, test authentik OIDC with WordPress's existing users and miniOrange configuration, preserving `board_director` Members roles. A user's Rooted Psyche Workspace identity or MailFlow access is not in itself WordPress board authorization. Personal Gmail sign-in must resolve to the same authentik person and WordPress user *only after explicit linking*.

### Rooted Psyche Workspace acceptance — 2026-11-26

**Production confirmed:** The separate Internal Google OAuth client for the `rootedpsyche.org` Workspace, authentik `google-rootedpsyche` source, new source property mapping `RootedOps - Google Workspace rootedpsyche.org verified email`, and authentik MailFlow expression policy were configured by the operator. Source labels appeared distinctly for all three Google options. The MailFlow application bindings shown were `mailflow-users` (order 0), verified edanks Workspace (order 10), and verified rootedpsyche Workspace (order 15), all enabled, with engine `Any`.

User `admin@rootedpsyche.org` authenticated through the new Google Workspace and MailFlow automatically created a **non-admin SSO-only user**; read-only SQL confirmed `username='admin@rootedpsyche.org', is_admin=f, password_hash IS NULL`. This verifies one positive new-user case, but does **not** establish that personally linked Google identities can be merged safely or that an unapproved personal Google nonmember is denied; those tests remain pending.

**Identity consolidation:** For this pilot, `admin@rootedpsyche.org` enrolled as a **separate** authentik person and acquired a separate MailFlow user. The established `RayDanks` person remains associated with `ray@edanks.com` and linked personal Google `raymonddanks@gmail.com`; eventually the Rooted Psyche Workspace Google identity must link to **that same** person, not create or retain two long-term identities. Do not delete either identity or reassign their provider-subject links without a preflight that verifies no unique app/mailbox data needs migration. Source verified-email mapping must be canonical-email aware before linking, or it could overwrite Ray's verified marker and cause MailFlow OIDC verification failure. Keep both operationally separate until a documented safe migration is tested.

**Next phase:** WordPress OIDC integration is planned but not yet configured; preserve existing miniOrange login, existing WP user IDs and explicit `board_director` role entitlements. MailFlow group or Workspace domain membership is not board role authorization.

## Consolidation decision — organizational roles and one Google OAuth source (2026-11-27)

**Owner's intended design supersedes the permanent three-Google-source architecture described in prior pilot sections.** Keep the working pilot intact during cutover. The target is **one External Google OAuth application owned by the Rooted Psyche Google Cloud project** and one corresponding authentik Google source; authenticate personal Gmail, edanks.com Workspace and rootedpsyche.org Workspace through it. Do not mix mailbox IMAP/app passwords with authentik SSO credentials; MailFlow mailbox access is separately authorized.

### Role-based access, not per-application membership

Authentik person = stable identity with zero or more explicitly linked Google accounts. Organization roles determine authorization; suggested groups are `rootedpsyche-board-director`, `rootedpsyche-spiritual-practitioner`, `dankmushrooms-cultivation`, `dankmushrooms-sales` (names illustrative; map to actual governance and staff policies). App access is derived by application policy bindings. For example:

| Role / relationship | MailFlow | WordPress board portal | Appsmith |
|---|---|---|---|
| Rooted Psyche board director | Yes | Yes, after approved WP user/role mapping | No by role alone |
| Rooted Psyche spiritual practitioner | Yes | No by role alone | Possibly, via practitioner-specific app policy |
| Dank Mushrooms cultivator | Per authorized org mailbox/role policy | No | Cultivation app access as required |
| Dank Mushrooms sales | Per authorized org mailbox/role policy | No | Sales app access as required |
| Person with verified, currently active edanks.com or rootedpsyche.org mailbox | Yes | No by mailbox alone | No |
| Individually approved external person | `mailflow-users` exception group | Separate explicit grant | Separate explicit grant |

Avoid hand-maintaining duplicate application-specific user memberships for people whose organizational role already confers access. A person may hold multiple roles; role removal is independent of their ability to authenticate with a different Google identity. Board portal authorization must remain explicitly mapped to existing WordPress `board_director` roles.

### Focused migration (four current authentik human identities)

1. Back up authentik and MailFlow state; record existing authentik user IDs, Google source links and MailFlow OIDC links. Keep `akadmin` local and current access paths working.
2. In the **Rooted Psyche-owned Google Cloud project**, change OAuth audience from Internal to External in Google Auth Platform → Audience **if the UI supports it for this project**. Use the already branded Rooted Psyche client/consent configuration. Confirm published status and any brand verification required for externally branded login with basic identity scopes (`openid email profile`); keep redirect URI `https://auth.danks.store/source/oauth/callback/google-rootedpsyche/`. If Google does not offer an audience switch, create a new External-audience project owned by Rooted Psyche rather than forcing or reusing edanks.com credentials.
3. Use `google-rootedpsyche` as the **single target authentik Google source**, retaining the same slug and client identifier where possible. Set user matching to **unique identifier**, never auto-merge by email. Remove per-Workspace-only verified-email source property mapping; replace it with generic upstream verified-email mapping that records per-source verified emails without overwriting a different canonical `email_verified_address`. The app's OIDC email scope must continue to report accurately `email_verified` for the canonical authentik email used by MailFlow. Use authentik source-linked unique subject, not mutable email, to authenticate known persons.
4. **Critical admission rule change before widening source to External:** existing MailFlow policy currently grants access based on `user.path=goauthentik.io/sources/google-rootedpsyche` plus verified email; this will no longer demonstrate an Internal Workspace source after the switch. Replace both `edanks` and `rootedpsyche` source-path policies with association/role-based policies using verified Workspace-specific organization evidence (for Google Workspace, trusted `hd` claim and source identity, or confirmed/maintained organizational account status) and explicit organization roles. Continue to allow `mailflow-users` as an exception. Do not enable a broad suffix-only grant after opening External OAuth.
5. For each existing authentik person (currently a small set), sign in through an existing still-working source, use **User Settings → Connected services** to link their corresponding Google account through the new consolidated source. Each authentik source connects one Google identity per person; if a person has multiple Google accounts under the same source, this source-connection model may need checking for whether multiple links to the same source are supported. Test before assuming a single source will allow all three linked Google logins for RayDanks. Avoid creating new authentik users through the login screen for already-associated persons.
6. Confirm every successful login resolves to the original authentik user ID and OIDC subject, existing MailFlow user, mailboxes and permissions. Check verified email mapping doesn't change the canonical user email or falsely mark an unrelated email verified. Independently test an unapproved personal Gmail identity can authenticate to authentik but is denied MailFlow access.
7. Only after successful login and negative tests disable redundant `google-edanks` and `google-personal` sources; keep their records until all source connections have been migrated and restore is proven. Do not delete Google Cloud projects/clients as a first migration step.
8. Offboarding: revoke the organizational mailbox/Workspace login and all derived **organizational role** grants. For a person with other legitimate roles or linked external identities, do **not** indiscriminately delete the common authentik identity, as that would revoke unrelated organization access. Disable the whole identity only when no active organizations/entitlements remain. Audit MailFlow sessions/app entitlements and WordPress role removal separately.

**Open functional dependency:** confirm authentik 2026.8 supports more than one linked Google user-subject from **the same OAuth source** on a single authentik user. Distinct source connections are the configuration proven in the pilot; do not turn off two working sources on an assumption. If this functionality is unsupported, preserve separate Google sources solely for multiple-login identity linkage, while *still* centralizing organizational role-to-application authorization.

### Verified constraint and revised migration target (2026-11-27)

**Correction to the proposed one-source design above:** authentik 2026.8 OAuth UserSourceConnection enforces a uniqueness constraint on **(user_id, source_id)**, which prevents a single authentik user from connecting multiple distinct Google identities to **one** authentik OAuth source. This is documented in upstream authentik issues [#20975](https://github.com/goauthentik/authentik/issues/20975) and [#22612](https://github.com/goauthentik/authentik/issues/22612). Do not remove the other authentik Google **sources** as previously proposed while the requirement is for RayDanks to use edanks Workspace, rootedpsyche Workspace and personal Gmail logins as the same authentik person.

**Revised pragmatic target:** The Rooted Psyche-owned **External Google Cloud OAuth app/client** can be the **single Google Cloud credential owner**, with multiple callback redirect URIs (one per authentik source: `google-edanks`, `google-rootedpsyche`, `google-personal`). Keep distinct authentik OAuth source records, one linked Google account per user+source, but update their client credentials to the shared External client after preregistering each distinct redirect. This should preserve user/source connections because source records/slugs remain unchanged; Google account `sub` is expected to remain stable across clients in the same Google identity platform, but verify each existing login and source connection in production before retiring old OAuth clients. Do not change all three source credentials at once, and keep `akadmin` recovery.

**Access architecture stays organizational, not app-centric:** Use Rooted Psyche board director, Spiritual Practitioner and Dank Mushrooms functional groups to derive application rights; retain `mailflow-users` only for explicit exceptions. Workspace mailbox association can additionally qualify for MailFlow without implying any WordPress board or Appsmith roles. No need to assign every board director individually to WordPress and MailFlow application groups if app policies can bind organizational roles. Existing WordPress user identities/roles still require explicit, safe one-time mapping.

**Security after External Google cutover:** source path by itself no longer proves which Workspace authenticates the account—any Google account could use any registered authentik source with a shared External OAuth client. The current MailFlow expression additionally demands the exact verified current email + organization-domain suffix, which provides ownership evidence but not ongoing Google Workspace membership. For Workspace membership assertions use trusted `hd` or administrator-maintained org attributes, or adopt the owner's explicitly accepted mailbox-owner/offboarding model and remove entitlements on Workspace removal. Test an unrelated Gmail identity denied. Do not silently treat username, source path or mere linked personal identity as organizational membership. Offboard organizational roles and mailboxes while preserving any unrelated organizational roles the same person still holds.

**Google Cloud audience:** If the Rooted Psyche Cloud project offers **Make external** under Audience, use that supported UI and complete publication/brand verification as applicable; otherwise use a new **Rooted Psyche-owned External project**. Do not assume audience is always mutable. With basic `openid email profile`, no Gmail mailbox access is requested.

