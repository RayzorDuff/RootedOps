# Google Workspace verified-email automation (pilot: edanks.com)

**Status:** Source-mapping installer committed, not applied to the live authentik server. First acceptance user: `cormac@edanks.com`; the successful prior manual example was `ray@edanks.com`.

This implements **one step of #139**: on first and subsequent Google sign-in through the **existing** `google-edanks` authentik source, record a **top-level** `email_verified_address` from Google's **Boolean** `verified_email` (v1 userinfo) or `email_verified` (OIDC) claim. It is not per-user configuration. It does not create app users, change flow policies, grant MailFlow/WordPress permissions, configure Gmail mailbox OAuth, or turn on open SSO provisioning.

## Before inviting Cormac

- Confirm the source is the established **edanks.com Internal Google Workspace OAuth** client with slug `google-edanks`. The mapping is deliberately restricted to addresses ending `@edanks.com`, and only reads claims from that source.
- Keep your existing authentik `RootedOps - Verified Email` **OIDC scope mapping** on its MailFlow provider. It returns `email_verified: true` only when the user's *current email* exactly matches `attributes.email_verified_address`.
- Preserve existing Google source user mappings, `RayDanks` and break-glass `akadmin`; the installer modifies only the source's user property mapping associations.
- In authentik Admin, create an **API token** with privilege to read the OAuth source and OAuth source property mappings and create/update those records. Use a short lifetime; do not store the token in `.env`, shell history, the repository or tickets. The script prompts without echo. Do not use someone else's Google OAuth client secret as an API token.

Once the PR is merged and pulled on the production host:

```bash
cd ~/RootedOps
python3 -m unittest tests/test_authentik_google_verified_email.py -v
# Read-only preview; paste the token at hidden prompt.
python3 scripts/authentik_google_verified_email.py
# Only after reviewing dry-run output:
python3 scripts/authentik_google_verified_email.py --apply
# Run again: should report already configured with no changes.
python3 scripts/authentik_google_verified_email.py
```

The installer requires HTTPS at `https://auth.danks.store`, exact source slug `google-edanks`, `provider_type=google`, and a non-conflicting mapping name. It creates the OAuth Source property mapping `RootedOps - Google Workspace edanks.com verified email` and **adds** it to existing source user mappings. It does not touch the MailFlow OIDC scope mapping. Existing settings are preserved; conflicting manually edited expressions fail closed rather than overwrite.

### First-user acceptance (after installation)

1. **Administrator:** verify no authentik `cormac@edanks.com` account or MailFlow account already exists. Record who is authorized to use MailFlow. As MailFlow admin, use Settings → Administration → Users → Invite, sending to an address the recipient can actually read.
2. **Recipient:** open the MailFlow invitation link **first** (`/register?invite=...`). In MailFlow **4.5.1**, invitations create a local account with a username and password, even though SSO is available. Register username **`cormac@edanks.com`**. MailFlow enrollment accepts an invitation email separately from the chosen username, so ensure the user enters the authorized username. Do not share or record their password.
3. **Recipient:** sign out and use `https://mail.danks.store/login` → **Sign in with RootedOps Identity** → authentik's Google button. Use exactly `cormac@edanks.com`. This may be the *first-ever authentik sign-in*: default social enrollment creates his authentik person, the new source mapping records his verified-email marker, and MailFlow's **Match existing / login_existing_only** mode matches the now-verified email claim against the previously registered canonical username. This removes the need for a separate authentik sign-in and explicit linked-SSO operation when the usernames match.
4. **Administrator:** verify Cormac now exists as a separate authentik user with top-level `email_verified_address: cormac@edanks.com` and an attached `google-edanks` source. **External user type is fine** for app SSO; it may not display authentik's internal dashboard. Do not grant administrator or board roles merely because of the Workspace domain.
5. **Recipient:** verify access is to **only his own MailFlow user**, with no admin controls and none of Ray's connected mailboxes. MailFlow login alone does not connect his `edanks.com` Gmail mailbox; that still needs separate mailbox OAuth or an eligible app password.

Optional read-only audit:

```bash
sudo docker exec mailflow-postgres psql -U mailflow -d mailflow -c "
SELECT u.username, u.is_admin, p.slug AS sso_provider,
       i.email AS linked_email, i.email_verified
FROM users u
LEFT JOIN user_identities i ON i.user_id=u.id
LEFT JOIN oidc_providers p ON p.id=i.provider_id
WHERE u.username IN ('ray@edanks.com','cormac@edanks.com')
ORDER BY u.username;"
```

**Do not** open MailFlow registration, set its OIDC provisioning mode to `open`, disable verified-email enforcement, manually UPDATE its DB identity table, or preauthenticate Cormac in authentik. If both verification claim variants are absent or false, source mapping returns an empty marker, MailFlow rejects login, and the operator should verify Google's upstream claims / source configuration instead of bypassing checks.

### Limitation and next phase

This is **automated email-claim propagation**, not end-to-end SSO invitation acceptance or identity provisioning. MailFlow 4.5.1's invitation registration route requires a local password; its sign-in flow is separate. A truly passwordless, invitation-constrained SSO activation that creates the intended MailFlow user and binds its issuer/subject requires a supported upstream enhancement or a securely designed integration. Track this as a separate #139 task. The present test uses MailFlow's **existing user matching by verified email** for first link: it is email-based bootstrap, not a general multi-provider identity merge. It must not be expanded to arbitrary providers/orgs without verified identity, explicit invitation and approval bindings.

For this initial pilot, the restricted edanks.com Google OAuth source, completed MailFlow invitation, and equality of canonical username with verified email are the safeguards. Investigate first-link replay/other-email behavior before using this mechanism for board/staff onboarding. Preserve local MailFlow admin login and authentik break-glass recovery throughout.

Upstream documentation: [OAuth Source property mappings](https://docs.goauthentik.io/users-sources/sources/protocols/oauth/), [Source mapping merge behavior](https://docs.goauthentik.io/users-sources/sources/property-mappings/), [Verified email OIDC](https://version-2026-8.goauthentik.io/add-secure-apps/providers/oauth2/verify-email-address/).
