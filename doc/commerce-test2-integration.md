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
