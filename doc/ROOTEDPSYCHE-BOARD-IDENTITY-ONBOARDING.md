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
- [x] Confirm that optional personal Google account association works without changing the user's canonical Workspace email, verification marker, or WordPress-linked identity.
- [ ] Personalize recipient greeting and Workspace address privately immediately before sending; **never** copy recipient lists or generated passwords back into GitHub.

## Short board-member email — send only after acceptance

**Subject:** Your Rooted Psyche email and board portal access

Hello [recipient],

Rooted Psyche has created a Google Workspace account for you: **[your-name]@rootedpsyche.org**. Your account setup instructions were sent separately. If you tried the activation link earlier and received an error, please try it again; we have adjusted the account setup requirements. Please set up two-step verification within one month of your initial sign-in.

You can use your new account with Google's familiar tools, including Gmail, Calendar and Drive, if you choose.

For email, visit **https://mail.rootedpsyche.org**. MailFlow can display your Rooted Psyche mailbox and, if you'd like, other mail accounts you connect yourself. You can also use your Rooted Psyche mailbox through Google's Gmail tools; neither approach is required over the other.

Your Rooted Psyche Workspace account is also your sign-in for Rooted Psyche services, including the **board portal** at **https://rootedpsyche.org/board/**. Choose **Sign in with RootedOps Identity**, select **Google Workspace — rootedpsyche.org**, and use your new Workspace account. Your existing board access will be preserved.

**Optional: use your personal Google account**

Please sign in with your new Rooted Psyche account first. If you prefer to use your personal Gmail account for future sign-ins, visit **https://auth.danks.store/** while signed in with your Rooted Psyche account. Open your account settings and look for connected accounts or social login connections. Choose the personal Google connection and sign in to your personal Google account when prompted. Once connected, you can choose the personal Google sign-in option when visiting the board portal. This is optional and does not change your Rooted Psyche email address. If you cannot find the connection option or encounter any problems, please reply to this email so we can help.

If you have any trouble signing in or accessing the board portal, please reply to this email.

Thank you,
Rooted Psyche

## Notes for implementation

The email uses the **current three-source Google login UI**. Do not describe a single Google button; that simplification is deferred. Its WordPress SSO instructions have passed the representative production pilot; personal linking has passed the representative production test; exact menu wording remains generic. If the final WordPress login button or callback differs, update this draft after testing. WordPress user IDs remain site-local; manage organizational board membership in authentik, and project/revoke its `board_director` privileges into WordPress.

**Pilot identity path:** rehearse first-time enrollment with a separate organization-issued Workspace account and an existing personal-email WordPress director account. Preapprove the association privately; do not require users to change WordPress email or create a second account. Existing administrator and linked identities are excluded from this rehearsal.


## Board group propagation pilot (2026-11-27)

Persistent OIDC login to existing WP ID 8 succeeded with Link Existing Users OFF. Keep account creation OFF. In authentik create an OAuth scope mapping named Rooted Psyche WordPress Board Groups, scope `rootedpsyche_groups`, expression:

```python
return {"groups": ["rootedpsyche-board-directors"] if ak_is_group_member(request.user, name="rootedpsyche-board-directors") else []}
```

Attach only to the dedicated Rooted Psyche WordPress provider, preserving verified email and other existing scopes. Request `openid email profile rootedpsyche_groups offline_access` in WP OIDC settings; offline access was subsequently enabled and refresh-token issuance verified. Check for duplicate groups claim from profile and resolve before activation. Repeat pilot login; run `scripts/wordpress_auth_claim_check.php` from PR #147 through PHP CLI in the Rooted Psyche WP container with ROOTEDOPS_WP_USER_ID=8. Require persistent subject, matching user claim subject, verified matching email, groups array and board group. Never print token contents. Do not enable bridge yet.

PR #147 now requires explicit ROOTEDOPS_AUTHENTIK_WP_MANAGED_IDS cohort (initially [8]); legacy IDs 2,4,5,6 remain unchanged until reconciled. The 300-second freshness guard is still a pilot limitation; production deployment requires tested refresh/revocation, coverage of protected resources and rollback. Keep current recovery login and miniOrange. Automatic creation remains deferred. No changes to MailFlow or Dank WooCommerce.


## Pre-provisioned Workspace identity pilot

Retain unique-identifier matching for all Google sources, the current authentication/enrollment flows and verified-email mapping. Do not enable general email linking. Operator confirmed Members logged-out content message now offers the WordPress login link. Google MFA enforced with one-month enrollment grace period.

Retrieve the exact primary email and immutable Google Directory ID for one already connected Rooted Psyche Workspace control account and the new pilot via authenticated Google Admin SDK users.get (read-only scope). Independently compare the control ID against the existing google-rootedpsyche OAuth source connection. Never assume directory IDs equal OAuth identifiers without this check. Keep identifiers private. Use scripts/authentik_workspace_preprovision.py in the authentik Django shell; set ROOTEDOPS_WORKSPACE_EMAIL, ROOTEDOPS_GOOGLE_IDENTIFIER, ROOTEDOPS_CONTROL_EMAIL, ROOTEDOPS_CONTROL_GOOGLE_IDENTIFIER and ROOTEDOPS_DISPLAY_NAME privately. Preview by default; ROOTEDOPS_APPLY=YES explicitly creates a new user, unusable local password, source connection and board group in a transaction. Existing users or identifiers are rejected. The dedicated WP provider must retain hashed_user_id subject mode; apply prints the private expected subject. Do not fabricate verified email. Check actual verification after source login; if missing, investigate source authentication mapping before enabling role projection.

Use scripts/wordpress_auth_subject_link.php with ROOTEDOPS_WP_USER_ID, ROOTEDOPS_OIDC_SUB and ROOTEDOPS_APPROVED_WORKSPACE_EMAIL, preview then explicit apply. This preserves the existing WP contact email and uses the native blog-prefixed subject option. Keep OIDC automatic linking and account creation OFF. Never bind the same subject to two WP users. The pilot bridge checks approved organizational email instead of contact email for explicitly prepared users. This is not a complete automatic provisioning or session revocation rollout; validate on live pilot and retain legacy directors and admin recovery until renewal/revocation, deployment persistence and complete authorization coverage are accepted. No real roster or identifiers in Git.


### Live verified-email repair acceptance (2026-11-27)

Pre-provisioned Workspace users initially lacked the verified-email marker: the default source authentication flow contained only login, whereas enrollment contained User Write. Operator created dedicated `rootedpsyche-workspace-authentication`, with existing-user-only User Write at order 10 and default source login at order 20, and an expression policy `rootedpsyche-workspace-verified-email-persistence` intended to restrict writes to mapped verified organizational email matching the pending user's canonical email. Runtime evaluation on, planning evaluation off for the write binding. Assigned only to `google-rootedpsyche`; matching and enrollment unchanged. Fresh production login to the existing personal-email WordPress account passed: both claims have matching subject, verified email true and board group true; contact-email comparison false intentionally. Verify exact policy binding and approved-email metadata before enabling role projection; retain independent admin recovery. Board library listing restored after mount recovery (#148). This is not yet acceptance of role synchronization or revocation.


## Production acceptance update (2026-11-27)

Role projection for two managed test accounts passed, including global and blog-prefixed OIDC subject metadata. The dedicated Workspace write-stage policy is bound and enabled. Session renewal is deployed for the test cohort at revision 6c5062a1d31845bb6d2847df4f7ba46e137144e3; browser access and document download continued beyond five minutes without interactive authentication. Account deactivation and group removal denied new authorization; restoring group membership restored sign-in. Existing-session negative renewal and direct-download revocation have not been conclusively observed; expired stored snapshots were reported, but not a subsequent denied renewal. Keep this as a focused security follow-up before broad enforcement. Desktop OAuth read-only Google Directory lookup and immediate credential reuse passed; no manual API Explorer lookup is needed. Personal Google linking passed representative production acceptance: the operator connected a personal Google account while authenticated as the organizational identity, then signed in through the personal source in a fresh session and accessed the Board Portal using the same existing WordPress account. Both stored claims retained matching subject, verified email and board group. Never link by email alone. Preserve Workspace canonical email, verification marker, stable subject and board group when connecting the personal source. The email above remains a draft until these conditions and roster reconciliation are satisfied.
