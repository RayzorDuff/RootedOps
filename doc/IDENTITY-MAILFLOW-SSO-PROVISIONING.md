# MailFlow passwordless activation with authentik application access controls

**Status:** Planned production configuration; **not enabled yet**. RootedOps #139 and #144. Verified 2026-11-26: `ray@edanks.com` and `cormac@edanks.com` authenticate through authentik and have separate MailFlow accounts; Cormac's `email_verified_address` was automatically propagated on first Google enrollment. This runbook moves *admission decisions* into authentik and makes MailFlow's own account creation fully SSO-driven.

## The model

MailFlow 4.5.1's OIDC **Open** provisioning branch creates a local `users` row with `username = lower(email)` and **`password_hash = NULL`** on first successful login with a verified email; it links the token issuer+subject in `user_identities`. It does not grant admin privileges to the first SSO-created user. If that verified email matches an existing MailFlow username, the code reuses that existing user and links its identity, so the upstream issuer is trusted to accurately verify email. **Open does not mean public registration should be enabled**: MailFlow's local registration must remain closed.

Open SSO alone is not invitation-limited and would let every user of an unrestricted authentik application provision an account. Therefore **deny unapproved users at authentik's MailFlow application before enabling Open in MailFlow**:

- authentik Application: `mailflow` (provider remains the existing `RootedOps Identity` confidential OIDC provider).
- Create an authentik group `mailflow-users`. Membership is approved and administered; a verified Google email address **alone never adds someone to this group**.
- Bind this group to the **authentik application**, using the **Policy / Group / User Bindings** tab. Do not merely hide the app or add a dashboard-only decoration. Verify the binding blocks OAuth authorization when the user is not in the group, including an app-initiated login via `mail.danks.store`.
- Only **after deny/allow verification**, switch MailFlow Settings → Administration → Single Sign-On → `RootedOps Identity` → **Provisioning mode: Open**. Leave provider enabled, `Require verified email` on, `Allow insecure connections` off, admin group claim unset and public registration closed.
- Optionally constrain MailFlow Allowed email domains to `edanks.com` **during the two-user Workspace-only pilot**. This is secondary defense, **not** a substitute for approved group membership, and would need deliberate expansion to support Rooted Psyche and external invited users.

No organizational mailbox is configured by OIDC login. Users connect their own mailbox via Gmail OAuth/app password or supported IMAP/SMTP. Org mailbox provisioning requires a separate approved process.

## Admin — current pilot preparation (do not skip order)

1. Keep working `ray@edanks.com` local MailFlow login and `akadmin` local authentik recovery paths. Confirm both existing SSO logins still work. Capture a backup of current identity and MailFlow PostgreSQL before making production authorization policy changes.
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
