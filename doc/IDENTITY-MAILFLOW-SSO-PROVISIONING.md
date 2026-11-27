# MailFlow passwordless activation with authentik application access controls

**Privacy note:** Any email-like address below is an illustrative, pseudonymous placeholder for a configuration or acceptance test, not an actual user's address. Keep real person-email mappings and invitation recipients in approved private operational systems; do not copy them into public repository docs or issue comments.

**Status (2026-11-26):** Production pilot passed. Authentik MailFlow application's policy engine is **Any**, with a `mailflow-users` group binding and an enabled expression policy for verified `google-edanks` Workspace identities. MailFlow OIDC Open provisioning is enabled; `workspace-user-c@edanks.com` authenticated and was created as a **non-admin without a local password**. Negative testing of a separate personal Google identity is deferred until the `rootedpsyche.org` and external personal Google sources are configured. No application changes are needed to repeat the successful Workspace flow. RootedOps #139 and #144. Verified 2026-11-26: `primary-user@edanks.com` and `workspace-user-b@edanks.com` authenticate through authentik and have separate MailFlow accounts; Cormac's `email_verified_address` was automatically propagated on first Google enrollment. This runbook moves *admission decisions* into authentik and makes MailFlow's own account creation fully SSO-driven.

## Acceptance evidence — edanks.com Workspace (2026-11-26)

The operator verified the following directly in production, without changing the original Ray/Cormac accounts:

| User | is_admin | password_hash IS NULL | Sign-in / origin |
|---|---|---|---|
| `primary-user@edanks.com` | `t` | `f` | Existing administrator, linked authentik SSO |
| `workspace-user-b@edanks.com` | `f` | `f` | Existing invitation-created user, later linked via verified Google SSO |
| `workspace-user-c@edanks.com` | `f` | `t` | **Newly auto-created from Google Workspace → authentik → MailFlow** |

The prior **pre-policy** test denied Ethan as an unapproved/non-group user. After the verified Workspace expression policy was created and bound, the authentik Application screen showed both bindings enabled — **group `mailflow-users` (order 0)** and **expression `MailFlow - Verified edanks Workspace` (order 1)** — with policy engine **Any**. Ethan then authenticated and MailFlow auto-provisioned him without a local password. This establishes a successful *positive* Workspace path, **not** a cross-provider negative test. Once an External personal Google source exists, test that a nonmember personal Gmail identity remains denied. Do not claim that test passed already.

The Workspace expression currently checks a verified-email marker and authentik enrollment source path `goauthentik.io/sources/google-edanks`. Its trust depends on the Google Cloud OAuth client remaining **Internal** to the specified Workspace, as well as protection against user-modified source paths and verification attributes. This source-specific policy must not be replaced by a generic email-domain suffix test.

**Future provider test:** Add a separately restricted `rootedpsyche.org` Workspace identity source, verify its own top-level verified-email mapping, configure a separate source-aware MailFlow application policy under **Any**, and test both allowed Workspace SSO provisioning and denial of an unapproved personal Google identity. WordPress board authorization remains separate.

## The model

MailFlow 4.5.1's OIDC **Open** provisioning branch creates a local `users` row with `username = lower(email)` and **`password_hash = NULL`** on first successful login with a verified email; it links the token issuer+subject in `user_identities`. It does not grant admin privileges to the first SSO-created user. If that verified email matches an existing MailFlow username, the code reuses that existing user and links its identity, so the upstream issuer is trusted to accurately verify email. **Open does not mean public registration should be enabled**: MailFlow's local registration must remain closed.

Open SSO alone is not invitation-limited and would let every user of an unrestricted authentik application provision an account. Therefore **deny unapproved users at authentik's MailFlow application before enabling Open in MailFlow**:

- authentik Application: `mailflow` (provider remains the existing `RootedOps Identity` confidential OIDC provider).
- Create an authentik group `mailflow-users`. Membership is approved and administered; a verified Google email address **alone never adds someone to this group**.
- Bind this group to the **authentik application**, using the **Policy / Group / User Bindings** tab. Do not merely hide the app or add a dashboard-only decoration. Verify the binding blocks OAuth authorization when the user is not in the group, including an app-initiated login via `mail.danks.store`.
- Only **after deny/allow verification**, switch MailFlow Settings → Administration → Single Sign-On → `RootedOps Identity` → **Provisioning mode: Open**. Leave provider enabled, `Require verified email` on, `Allow insecure connections` off, admin group claim unset and public registration closed.
- Optionally constrain MailFlow Allowed email domains to `edanks.com` **during the two-user Workspace-only pilot**. This is secondary defense, **not** a substitute for approved group membership, and would need deliberate expansion to support Rooted Psyche and external invited users.

No organizational mailbox is configured by OIDC login. Users connect their own mailbox via Gmail OAuth/app password or supported IMAP/SMTP. Org mailbox provisioning requires a separate approved process.


## Domain-wide access: trusted Google Workspace accounts plus individually approved users

**Requested production policy, 2026-11-26:** All verified `edanks.com` Workspace identities should access MailFlow automatically, and later all verified `rootedpsyche.org` Workspace identities likewise. Personal Gmail users and non-Workspace identities must remain individually approved through `mailflow-users`. This authorization is distinct from authentik's ordinary user type (External is fine) and from a MailFlow mailbox connection.

**Important:** An expression checking only `email.endswith("@edanks.com")` would be too weak: an authentik user with an independently connected identity may have that email address recorded without demonstrating the intended Workspace source. For the current pilot, `google-edanks` uses an **Internal** OAuth client restricted to the edanks.com Workspace. Its source property mapping sets `email_verified_address` only from Google's verified email claim. Cormac's actual user path is `goauthentik.io/sources/google-edanks`, as shown in production.

### Configure the Workspace authorization policy (authentik UI)

1. Open **Customization → Policies → Create → Expression Policy**.
2. Name: `MailFlow - Verified edanks Workspace`.
3. Expression:
   ```python
   user = request.user
   email = (user.email or "").strip().lower()
   verified = (user.attributes.get("email_verified_address") or "").strip().lower()
   source_path = user.path or ""
   return (
       email.endswith("@edanks.com")
       and email == verified
       and source_path == "goauthentik.io/sources/google-edanks"
       and user.is_active
   )
   ```
   This is deliberately **source-enrollment-bound**, not a universal provider-independent Workspace-membership proof. Users originating from other authentik sources who later link edanks.com need a reviewed alternative source-connection check. For this initial Workspace's normal Google enrollment it is sufficient. Protect changes to user path and verified-email attributes as privileged operations; never let users self-edit them.
4. Open **Applications → Applications → MailFlow**. Confirm existing binding `mailflow-users` remains enabled, non-negated, failure result **Don't Pass**.
5. Under **Policy / Group / User Bindings**, bind existing Expression Policy `MailFlow - Verified edanks Workspace`, enabled, non-negated, failure result **Don't Pass**.
6. Edit the **MailFlow Application** and set **Policy engine mode = Any**. With two bindings, the effect is: verified edanks Workspace **OR** explicit `mailflow-users` membership. **All** would require both and defeat domain-wide access. Inspect any additional bindings to avoid accidental broader grants.
7. Keep MailFlow SSO **Open** provisioning mode, **Require verified email = on**, public password registration **closed**, admin group claim unset. The WordPress / ERP / Appsmith authorization policies remain separate and unchanged.
8. **Safety tests:** In a private browser, an existing verified `edanks.com` user who is **not** in `mailflow-users` (e.g., Ethan) should gain access after signing through the trusted edanks Workspace source and should receive their own MailFlow user with `password_hash IS NULL`. An unapproved personal Gmail identity should be denied the MailFlow OIDC authorization. Ray and Cormac should continue to see their existing MailFlow users with unchanged mailboxes. Test a fake/unverified `@edanks.com` profile not enrolled from this source is denied. Do not drop the group binding; it will be needed for invited personal identities.
9. Later, add the verified `rootedpsyche.org` Workspace as a **separate source** with its own provider restricted to that tenant, source-specific verified-email mapping and a **separately tested** application policy. Bind its policy to the same MailFlow Application (still Any). Do not treat an `@rootedpsyche.org` suffix alone as proof of identity or board membership; MailFlow access and WordPress governance roles are independent.

**Rollback:** Disable the new Workspace expression binding (leave `mailflow-users` binding enabled) to return immediately to individually approved MailFlow access. If broader SSO provisioning itself must stop, change MailFlow back to **Match existing**, without deleting existing accounts or SSO links.

This is a proposed operational config, **not yet deployed by GitHub or proven for Ethan**. It must be verified in the production authentik UI; because the application policy is authoritative, test denied users before inviting general public Google identities.

## Admin — initial group-gated pilot history

1. Keep working `primary-user@edanks.com` local MailFlow login and `akadmin` local authentik recovery paths. Confirm both existing SSO logins still work. Capture a backup of current identity and MailFlow PostgreSQL before making production authorization policy changes.
2. In authentik Admin → **Directory → Groups** create `mailflow-users`. Add **RayDanks** and **CormacDell** (the two **existing** authentik identities) as members. Do **not** assign superuser/administrator access or inherit organization-wide groups. Confirm user membership in each user profile.
3. authentik Admin → **Applications → Applications → MailFlow → Policy / Group / User Bindings** → **Create or bind → Bind existing group** → choose `mailflow-users`. Enable the binding; no "Negate". If more than one binding exists, audit all bindings and policy engine mode (`Any` lets any binding grant access; `All` requires all bindings).
4. **Negative authorization test before changing MailFlow provisioning:** A known unapproved authentik test identity **not** in `mailflow-users` must be denied an OIDC authorization *initiated from `https://mail.danks.store/login`*, without issuing an identity token. Test with a separate incognito session. **Do not temporarily remove Ray or Cormac to simulate denial.** If no unapproved test identity is available, keep MailFlow in **Match existing** until this denial can be verified.
5. **Positive test** before switching provisioning: confirm Ray and Cormac (members) can still sign into their **existing** MailFlow accounts through RootedOps Identity, with the same MailFlow UUIDs and original mailbox connections. If either fails, revert/repair the authentik binding while leaving MailFlow on Match existing.
6. In MailFlow Settings → Administration → Users, check **Open registration remains disabled**. In **Single Sign-On**, edit `RootedOps Identity` and change **Provisioning mode** from **Match existing** to **Open**. Keep **Require verified email** enabled and admin group claim fields empty; do not change issuer, client credentials, signing or flows.
7. Retest Ray and Cormac logins, roles and inbox isolation. For an **actual account-creation test**, approve a third test person in authentik and the `mailflow-users` group, confirm no corresponding MailFlow user exists, have them sign in through OIDC, and check a user row is created **without** a local password. Ray/Cormac's existing accounts prove compatibility, not new-user auto-provisioning.

### Verification commands — read-only

```bash
sudo docker exec mailflow-postgres psql -U mailflow -d mailflow -c "
SELECT u.username, u.is_admin,
       (u.password_hash IS NULL) AS sso_only_no_local_password,
       p.slug AS sso_provider, i.email_verified
FROM users u
LEFT JOIN user_identities i ON i.user_id = u.id
LEFT JOIN oidc_providers p ON p.id = i.provider_id
ORDER BY u.username;"
```

This intentionally reports password **presence**, not hashes, and avoids listing OIDC tokens or mailbox credentials. Existing Ray and Cormac users may still have passwords from their initial invitation registrations. Newly *auto-provisioned* users should have `sso_only_no_local_password = t`.

Check MailFlow administration → Users for separate identities. Keep public registration closed, and verify that arbitrary `edanks.com` accounts do not gain MailFlow access just because Google identifies them.

## New-user procedure after group gate and Open provisioning are tested

1. The **administrator** approves the person and independently verifies the real-world identity, trusted Google/other provider, organization and MailFlow entitlement.
2. The person authenticates once with authentik's approved source and completes default first-enrollment (including authentik username); the verified-email source mapping populates `email_verified_address`. An external user type is sufficient for MailFlow and does not grant authentik dashboard access.
3. The administrator adds the now-existing authentik person to `mailflow-users`. This is the approval/activation step; there is **no MailFlow invitation**, MailFlow-specific username, or password. This may be done before first Google login only if an approved pre-provisioning and safe source-linking process exists; **do not automatically merge accounts based on an email address**.
4. The person visits `https://mail.danks.store/login` → **Sign in with RootedOps Identity** → authentik → their linked identity. On first approved login, MailFlow creates the local user directly and links its stable OIDC issuer/subject. On later visits the linked identity is reused.
5. Organization mailbox access is separately granted; personal mailboxes may be connected by the individual.

For one-click invited SSO-first activation, extend authentik's own invitation/approval process to bind source identity and `mailflow-users` membership safely. No app-level email is technically required when the administrator can verify/approve users out-of-band. Never assume a person belongs to an organization simply because an upstream provider returns that organization's email domain.

## Security and rollback

**Security boundary:** MailFlow's Open provisioning trusts the authentik provider's signed `email_verified` and its OIDC audience/issuer. The group binding is the actual approved-user gate. A user must not be able to assign themselves `mailflow-users` via OAuth source mappings, self-service group editing or an unrestricted authentik enrollment flow.

Existing MailFlow OIDC linkage may be looked up **before** Open mode. Never auto-link external identities to a current user by sharing a mutable email address unless the trusted provider truly verifies current ownership and the entitlement is approved. Review the risk when federating multiple identity providers. Enforce MFA in authentik when ready; do not assume external Google authentication alone proves user is an organizational member.

**Rollback:** Switch the MailFlow OIDC provider back to **Match existing / login_existing_only** first (this stops *new* SSO account creation while leaving linked SSO logins functional). Restore authentik group binding to the last tested safe policy if necessary. Leave existing user records and links untouched. Do not delete MailFlow users or perform database UPDATEs as a shortcut.

**Not implemented:** application-specific invitations with automatic authentik source linking and group assignment; provider-independent approval; organizational mailbox auto-attachment; SSO-only role and offboarding automation. Track via #139/#144.

References:
- https://version-2026-8.goauthentik.io/add-secure-apps/applications/manage_apps/
- https://version-2026-8.goauthentik.io/customize/policies/bindings/
- https://github.com/maathimself/mailflow/tree/v4.5.1
