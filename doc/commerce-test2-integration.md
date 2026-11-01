# Commerce integration on test2

This development checkpoint starts at RootedOps main
`482d8388305d447b88cbb37ebd20c316e636377d` (merged #43/#44). Existing native
component evidence and private override commands remain in test2-shared-readiness.md.
Do not recreate databases, replay restore, touch SignatureGate's schema/role/app
or infer end-to-end acceptance from the component proofs.

Commerce adapters now accept exact HTTPS `erp-test`/`shop-test` and
`erp-test2`/`shop-test2` origins. URL credentials, non-443 ports, path/query/fragment,
lookalike/production hosts and mixed test/test2 catalog/media pairs refuse before
transport. Native catalog/media harnesses resolve the target from matching
generated receipt/environment values, rather than a hardcoded retired hostname.

The inbox worker configuration accepts `erp_base_url`, defaulting to the existing
test origin for compatibility. Set it explicitly to `https://erp-test2.danks.store`
for this host. The MP financial identity link derives its ERP site from that same
validated origin; it no longer silently identifies test2 ERP documents as test.
Database allowlists and loopback receiver binding are unchanged. Restored MP DB
names are not renamed to bypass runtime guards; use a reviewed synthetic database
or separately reviewed endpoint support for native lifecycle acceptance.

Authenticated Woo regressions cover direct initial paid/processing ingestion,
duplicate payload identity and pending-to-paid revision changes. Paid state alone
remains unverified payment evidence and cannot acknowledge physical fulfillment.
The corrected Ecwid workflow in MushroomProcess main needs its own regression
run; no real production order is replayed by these tests.

Open native gates: test2 TLS/browser ingress, catalog/media parity, order-to-MP
reservations and explicit physical acknowledgement, ERP financial identity replay,
and Clover sandbox evidence. These code checks do not establish those results.
Do not enable restored n8n workflows or production-bound Appsmith actions.

## Ingress preparation and current acceptance boundary

The ingress renderer supports the exact four-host `-test` or `-test2` groups,
using separate certificate names (`commerce-staging` / `commerce-staging-test2`).
Mixed groups, production names and NGINX directive injection refuse. Its HTTP
renderer serves only the ACME challenge directory; other HTTP paths return 403.
The default TLS configuration exposes authenticated Woo REST/media routes only.
`--browser-shop` is explicit: only the isolated shop hostname proxies browser
paths, while ERP/Appsmith/n8n roots remain 403. XML-RPC and HTTP WP cron are blocked.
WordPress login still authenticates administration. No Docker ports or external
application network are added.

Before applying, verify authoritative A/AAAA records, conflicts in enabled NGINX
sites, the installed initialized-shop receipt, image identity, internal network
and outbound controls. Initial certificate issuance needs an ACME-only vhost and
`/var/www/rootedops-acme`; do not use the public shop proxy to expose first-run setup.
Issue a certificate for the matching four hosts, install a closed TLS vhost, and
verify trusted HTTPS to **each** name before writing a truthful `tls-acceptance.json`
(`tls_verified: true`, `domains`: the four exact names). The refresh command
requires this receipt plus an existing matching vhost/certificate and rolls back
its configuration if NGINX validation/reload fails. It does not issue certificates
or turn a failed TLS probe into acceptance.

Once those prerequisites are verified on this host, run from the reviewed source:

```bash
sudo python3 scripts/commerce_staging_ingress.py .test-deployment
sudo python3 scripts/commerce_staging_ingress.py .test-deployment --apply --browser-shop
sudo python3 scripts/commerce_woo_native_smoke.py .test-deployment
sudo python3 scripts/commerce_woo_media_smoke.py .test-deployment
```

Revalidate the browser homepage, authenticated REST, unauthenticated REST rejection,
other host roots 403, and unchanged internal networking. Re-run ingress refresh
after a container recreation changes its private address. To close browser access,
refresh without `--browser-shop`; no database restoration is involved. The default
refresh also closes public media paths, so API-only operation is not storefront
acceptance.

Current code validation: 83 commerce tests (82 pass, one local PHP-dependent skip)
and 18 recovery tests pass. This is offline evidence, not a Test2 integration run.
Test2's console reports that sudo requires reauthentication. No ingress or
certificate change has been applied during this checkpoint, and no native smoke
result is claimed. Keep ERP maintenance mode and disabled production integrations
until their narrowly scoped lifecycle validation is prepared.

New read-only DNS evidence, 2026-11-01: queried both authoritative servers
`elijah.ns.cloudflare.com` and `asa.ns.cloudflare.com` directly with recursion
disabled. ERP, Appsmith, n8n and shop `-test2` each return A `23.92.26.193` on
both authorities, with no AAAA answers. This verifies DNS only; it does not verify
port reachability, TLS issuance or browser routing.

## Review checkpoints and CI evidence

- RootedOps PR [#45](https://github.com/RayzorDuff/RootedOps/pull/45):
  tested implementation commit `9c9a7258f92e96552c753e58f4b0b417538171ba`, branch
  `feature/commerce-test2-e2e`. [Foundation CI](https://github.com/RayzorDuff/RootedOps/actions/runs/41268034253)
  and [recovery CI](https://github.com/RayzorDuff/RootedOps/actions/runs/41268034219)
  succeeded. [Native disposable integration CI](https://github.com/RayzorDuff/RootedOps/actions/runs/41268034242)
  was still running at this checkpoint; inspect its final result before merge.
- MushroomProcess PR [#111](https://github.com/RayzorDuff/MushroomProcess/pull/111):
  `2c23b11c8c15ee30e76476c070ad28879e5afe87`, branch
  `feature/ecwid-paid-at-creation-regression`, based on main
  `074367383af32e968886b12680020bcea5f9acad`. Ecwid order, catalog and fulfillment
  visibility Node smoke tests pass locally. The changed executable test is already
  included by commerce-postgres CI. No workflow/export/production branch changes.
- SignatureGate remains at the separately documented readiness baseline. This
  checkpoint neither changes its database/schema/role nor establishes browser E2E.

These review commits are not deployed Test2 acceptance SHAs. Preserve the native
image IDs, installed versions and private override commands in
[test2-shared-readiness.md](test2-shared-readiness.md). Native integration evidence
must record the actual source/image state at execution, not substitute these CI
results for a staging run.
