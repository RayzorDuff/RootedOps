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

Rooted Psyche has created a Google Workspace account for you: **[your-name]@rootedpsyche.org**. Your account setup instructions were sent separately.

You can use your new account with Google's familiar tools, including Gmail, Calendar and Drive, if you choose.

For email, visit **https://mail.rootedpsyche.org**. MailFlow can display your Rooted Psyche mailbox and, if you'd like, other mail accounts you connect yourself. You can also use your Rooted Psyche mailbox through Google's Gmail tools; neither approach is required over the other.

Your Rooted Psyche Workspace account is also your sign-in for Rooted Psyche services, including the **board portal** at **https://rootedpsyche.org/board/**. Choose **Sign in with RootedOps Identity**, select **Google Workspace — rootedpsyche.org**, and use your new Workspace account. Your existing board access will be preserved.

**Optional: use your personal Google account to sign in as the same person**

1. Sign in to **https://auth.danks.store/** using your new Rooted Psyche Workspace account.
2. Open **User interface → Settings → Connected services**.
3. Choose **Connect** next to **Google — Personal Accounts**, select your personal Google account and approve the connection.
4. On later sign-ins, you can choose either the Rooted Psyche Workspace or personal Google sign-in. Both should open the same Rooted Psyche identity and board access.

To avoid creating a second account, make that connection while signed into your existing Rooted Psyche identity, rather than enrolling separately with personal Google first.

If anything does not work, please reply rather than creating a second Rooted Psyche user.

Thank you,
Rooted Psyche

## Notes for implementation

The email uses the **current three-source Google login UI**. Do not describe a single Google button; that simplification is deferred. Its WordPress SSO instructions are **conditional**, not yet deployed. If the final WordPress login button or callback differs, update this draft after testing. WordPress user IDs remain site-local; manage organizational board membership in authentik, and project/revoke its `board_director` privileges into WordPress.

**Pilot identity path:** use an existing approved operator's `rootedpsyche.org` Workspace login linked through authentik **Connected services** to their existing principal, preserving the primary person's OIDC subject and canonical verified email. Do **not** attempt this with an already independently enrolled Google identity or before source mappings have been verified safe for multiple Workspace credentials. If the operator does not yet have a WordPress user eligible for board access, explicitly reconcile to the intended existing WP identity; do not auto-link via mutable email and do not elevate an admin account via a test.
