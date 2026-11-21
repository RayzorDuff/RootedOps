# AGENT_SUMMARY

UNCERTAIN: Issue #20 is an open multi-month epic, not a localized defect. Four of the
five documented stop conditions are met — 11 open draft PRs are already implementing
its remaining items (threshold is 3+), the unchecked acceptance work requires external
services and credentials that are explicitly unavailable, a coherent increment spans
well over ~5 files, and there is no single determinable "correct behavior" to restore.

**No code changes were made. Nothing was committed.**

## What I did

Full orientation and verification were performed before stopping; only the fix was
withheld.

- Read `README.md`, `Makefile`, `doc/commerce-staging-handoff.md`,
  `doc/commerce-order-contract-rehearsal.md` and the commerce doc set.
- Surveyed the tree, then read the code the issue's live checkpoint points at:
  `integrations/commerce/inbox.py`, `orders.py`, `runtime.py`,
  `editorial_projection.py`, `staging_origin.py`,
  `erpnext/apps/rootedops_commerce/rootedops_commerce/order_service.py`,
  `scripts/commerce_installed_order.py`, `nginx/*.conf`, `.env.example`.
- Read the tests (`tests/test_commerce_*.py`, `integrations/commerce/test_inbox_postgres.py`,
  `erpnext/apps/rootedops_commerce/rootedops_commerce/tests/`) and both commerce CI workflows.
- Ran the suite: `python -m unittest discover -s tests -p "test_commerce*.py"`.

## Why there is no fix to make

### 1. No defect exists to fix

`git diff main..HEAD` is empty — this branch is identical to `main`, so no regression
was introduced for me to repair. The 146 modified files in `git status` are **not real
changes**: `git diff --ignore-cr-at-eol --stat` is empty, so the entire 15,335-line
"diff" is CRLF-at-EOL churn from checkout on Windows (`core.autocrlf=false`, no
`.gitattributes`). Anyone finishing this task must avoid `git add -A`, which the task
file's step 5 recommends — it would commit a 146-file line-ending rewrite.

### 2. The test suite has no failure attributable to the issue

221 tests ran: 10 failures, 7 errors. All 17 are POSIX-only assertions failing on
Windows, not logic defects:

- `ModuleNotFoundError: No module named 'fcntl'` (`test_commerce_woo_recurring`)
- mode-bit assertions — `438 != 384` (0o666 vs 0o600), `438 != 420` — in
  `test_commerce_foundation`, `test_commerce_staging_media_inventory`,
  `test_commerce_wordpress_offline`
- `ValueError: Classification directory must be private (0700)` / `Receipt directory
  must be 0700` in `test_commerce_tax_classification`, `test_commerce_tax_policy_ingress`,
  `test_commerce_production_draft_import`
- tar device/FIFO/symlink handling in `test_commerce_backup`, `test_commerce_conversion`

CI (`.github/workflows/commerce-foundation.yml`) runs `make commerce-test` on
`ubuntu-latest`, where these pass. There is no red test pointing at a fix.

### 3. The remaining work is already claimed by 11 open draft PRs

`gh pr list --repo RayzorDuff/RootedOps --state open` returns 11 drafts; at least five
name this issue in their body ("Part of #20", "Tracks #20"):

| PR | Title |
| --- | --- |
| #124 | Preserve commerce identities when Woo moves to dankmushrooms.net |
| #120 | Continue approved Woo order updates on the commerce timer |
| #119 | Publish MP dispatch and availability to Woo with separate label preparation |
| #118 | Queue signed Woo orders for review after the launch pilot |
| #117 | Prepare the Dank storefront switch and rollback |
| #116 | Gate the first live Woo order across ERP, Clover and MushroomProcess |
| #115 | Project committed MushroomProcess shipments as ERP receipts |
| #114 | Draft Clover settlement journals from reviewed funding detail |
| #113 | Reconcile verified Clover sandbox captures into ERP clearing |
| #112 | Map reviewed Woo drafts and test native ERP delivery |
| #111 | Run the automatic unpaid WooCommerce order pilot |

This matters because of what I had scoped as the one viable repo-only increment. The
issue's November 15, 2026 checkpoint lists item 1 as "Deliver authenticated Woo order
lifecycle webhooks through the RootedOps inbox," and
`scripts/commerce_installed_order.py:178` still records `automatic_webhook_route=False`
— `integrations/commerce/runtime.py` binds the receiver to `127.0.0.1:8100` with no
nginx route and no Woo-side webhook registration. PR #111 is precisely that work: "Use
native WooCommerce order-created and order-updated webhooks with signed, durable
receipt and independent MushroomProcess and ERP outcomes." Implementing it here would
duplicate an in-flight PR and conflict with #112, #118 and #120, which stack on it.

### 4. The acceptance criteria require external services and explicit authorization

Every unchecked box needs infrastructure this environment cannot reach, and the issue
says so itself: "Repository-only development can continue while the disposable test
Linode is offline; merchant/plugin/live payment checks must await a new isolated
staging host and explicit authorization." Specifically required: the offline disposable
Linode, Ecwid API credentials, WooCommerce REST keys, Clover sandbox and merchant
credentials, a reversible DNS cutover for `danks.store`, and ERPNext `bench migrate`
plus MushroomProcess `054_commerce_operational_bridge.sql`.

### 5. A single safe commit cannot satisfy the acceptance criteria

Acceptance demands reconciled Ecwid parity, live Clover transactions mapped
exactly-once into ERPNext and MushroomProcess, correct `danks.store` and QR
resolution, verified backup/restore, and a confirmed merchant agreement. The repo
already carries roughly 2,400 lines of commerce integration code plus the
`rootedops_commerce` Frappe app across 149 files; closing the epic is a program of
work, not one logical change.

## Concerns for a reviewer

- `doc/commerce-staging-handoff.md:228` states the inbox "binds 127.0.0.1:8100 only …
  **never expose it as production ingress**." Exposing it is a deliberate owner-gated
  decision, so an agent should not unilaterally add that ingress — another reason to
  defer to PR #111.
- The CRLF artifact in §1 is a live trap for the next contributor on a Windows
  checkout. Adding a `.gitattributes` with `* text=auto` would prevent it, but that is
  unrelated to this issue and would itself touch every file, so I left it alone.
- I found no bug in the code I read. `inbox.py`, `orders.py` and `order_service.py`
  already handle duplicate receipts, lease loss, dead-lettering and replay,
  stale/same-revision conflicts, and refuse to create financial documents from a
  storefront status. The `revision_conflict` error code in `Inbox.fail` is declared but
  never raised; staleness is instead handled downstream
  (`order_service.py:111`, MP ingest returning `stale`). That is unused-code tidiness,
  not a defect, and not worth a speculative commit.
