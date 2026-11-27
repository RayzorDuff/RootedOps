# Rooted Psyche board identity onboarding — draft communications and acceptance

**Status: Draft; do not send until Rooted Psyche WordPress authentik SSO and board membership/role enforcement have passed acceptance (RootedOps #146).**

**Privacy rule:** No real users' primary, secondary, Workspace or personal email addresses belong in this tracked document, including examples, screenshots or test logs. Use `[your-name]@rootedpsyche.org` or `[recipient]` as placeholders. Never commit Google temporary passwords, authentication links, OAuth client secrets, or personal recovery addresses.

## Pre-send operations checklist

- [x] Initial Rooted Psyche Google Workspace accounts have been created by the operator and onboarding instructions issued privately. User reported four board accounts; screenshots document a subset of the provisioning confirmations. Do not infer any board role assignment from account creation.
- [x] Existing Google Workspace -> authentik -> MailFlow SSO path was tested with a separate non-admin Workspace pilot account.
- [ ] Confirm each intended board recipient's Workspace sign-in has been accepted and the appropriate board director appointment/role approved. Do not store private email correspondence or personal address mappings in Git.
- [ ] Confirm the board director authentik group exists and the approved board roster has been reconciled to the existing WordPress board director user IDs, without duplicate WP users.
- [ ] Confirm WordPress's dedicated authentik OIDC provider works; test approved board user, non-board user, logout/re-login, existing session revocation after authentik group removal, and emergency local admin access.
- [ ] Confirm `https://mail.rootedpsyche.org` is reachable and can access a new Workspace mailbox using the supported MailFlow mailbox connection process. Authentik SSO alone does not grant Gmail API mailbox access; when applicable, users may need app passwords or separate mailbox OAuth authorization.
- [ ] Confirm that optional personal Google account association works without changing the user's canonical Workspace email, verification marker, or WordPress-linked identity.
- [ ] Personalize recipient greeting and Workspace address privately immediately before sending; **never** copy recipient lists or generated passwords back into GitHub.

## Short board-member email — send only after acceptance

**Subject:** Your Rooted Psyche email and board portal access

Hello [recipient],

Rooted Psyche has created a Google Workspace account for you: **[your-name]@rootedpsyche.org**. Your account setup instructions were sent separately. If you tried the activation link earlier and received an error, please try it again; we have adjusted the account setup requirements. Please set up two-step verification within one month of your initial sign-in.

You can use your new account with Google's familiar tools, including Gmail, Calendar and Drive, if you choose.

For email, visit **https://mail.rootedpsyche.org**. MailFlow can display your Rooted Psyche mailbox and, if you'd like, other mail accounts you connect yourself. You can also use your Rooted Psyche mailbox through Google's Gmail tools; neither approach is required over the other.

Your Rooted Psyche Workspace account is also your sign-in for Rooted Psyche services, including the **board portal** at **https://rootedpsyche.org/board/**. Choose **Sign in with RootedOps Identity**, select **Google Workspace — rootedpsyche.org**, and use your new Workspace account. Your existing board access will be preserved.

**Optional: use your personal Google account**

Please use your new Rooted Psyche email address the first time you sign in. If you prefer to use your personal Google account in the future, you can link it to your Rooted Psyche sign-in. Please contact us if you would like help with that.

If you have any trouble signing in or accessing the board portal, please reply to this email.

Thank you,
Rooted Psyche

## Notes for implementation

The email uses the **current three-source Google login UI**. Do not describe a single Google button; that simplification is deferred. Its WordPress SSO instructions are **conditional**, not yet deployed. If the final WordPress login button or callback differs, update this draft after testing. WordPress user IDs remain site-local; manage organizational board membership in authentik, and project/revoke its `board_director` privileges into WordPress.

**Pilot identity path:** rehearse first-time enrollment with a separate organization-issued Workspace account and an existing personal-email WordPress director account. Preapprove the association privately; do not require users to change WordPress email or create a second account. Existing administrator and linked identities are excluded from this rehearsal.


## Board group propagation pilot (2026-11-27)

Persistent OIDC login to existing WP ID 8 succeeded with Link Existing Users OFF. Keep account creation OFF. In authentik create an OAuth scope mapping named Rooted Psyche WordPress Board Groups, scope `rootedpsyche_groups`, expression:

```python
return {"groups": ["rootedpsyche-board-directors"] if ak_is_group_member(request.user, name="rootedpsyche-board-directors") else []}
```

Attach only to the dedicated Rooted Psyche WordPress provider, preserving verified email and other existing scopes. Request `openid email profile rootedpsyche_groups` in WP OIDC settings. Check for duplicate groups claim from profile and resolve before activation. Repeat pilot login; run `scripts/wordpress_auth_claim_check.php` from PR #147 through PHP CLI in the Rooted Psyche WP container with ROOTEDOPS_WP_USER_ID=8. Require persistent subject, matching user claim subject, verified matching email, groups array and board group. Never print token contents. Do not enable bridge yet.

PR #147 now requires explicit ROOTEDOPS_AUTHENTIK_WP_MANAGED_IDS cohort (initially [8]); legacy IDs 2,4,5,6 remain unchanged until reconciled. The 300-second freshness guard is still a pilot limitation; production deployment requires tested refresh/revocation, coverage of protected resources and rollback. Keep current recovery login and miniOrange. Automatic creation remains deferred. No changes to MailFlow or Dank WooCommerce.
