# Installed commerce 0.3.1 and Ecwid source audit

Baseline: RootedOps main `f46f7af` includes merged #46/#47. The last verified native
ERP run used a candidate API preview; it did not establish an installed upgrade.
This checkpoint prepares the installed update and records the actual export audit.
It does not mark the installed upgrade, order lifecycle or cutover passed.

## Narrow app upgrade

Run only in the authorized Commerce Screen session, after obtaining the lock:

```bash
~/bin/test2-console-lock commerce
screen -r commerce
cd /home/rootedops/RootedOps
sudo -v
# Use the reviewed source branch/worktree containing these scripts.
sudo python3 scripts/commerce_test2_upgrade.py .test-deployment
sudo python3 scripts/commerce_test2_upgrade.py .test-deployment --apply
sudo python3 scripts/commerce_erp_native_fixture.py .test-deployment
sudo python3 scripts/commerce_erp_native_fixture.py .test-deployment
```

The updater refuses unknown source/version combinations, an active scheduler or
outbound integrations, wrong Compose identity, public ports or external networking.
It requires the already installed offline `flit_core` build backend before making
any change. If absent, stop and stage a verified official build-backend wheel;
do not grant the application external network access or install arbitrary packages.
Only the three app files changed in #47 are copied. No DocType/dependency changed,
so no schema migration or MariaDB rebuild is performed. Record fingerprints cover
catalog, customers, contacts/addresses, orders/invoices/payments and their lines.
Record hashes stay in private evidence; public reports must contain only results.
The app archive and package operation logs are saved under the existing private
deployment directory. A failed update attempts code/package rollback, never a
whole database restore. Only the ERP backend is restarted; Appsmith, n8n,
SignatureGate and Docker networks are untouched.

The fixture without candidate flags now requires installed module **and package**
version 0.3.1 and the reviewed API hash. Its report records both versions/hash and
marks installed-app acceptance only in that case. HTTP ERP authentication remains
a separate gate. Repeat runs must preserve Item/Price counts and Woo product 16.

Detach only this workstream's Screen with `screen -X detach`, then exit the locking
shell. Do not use Ctrl+A,D through Weblish: Linode's outer console layer may
intercept it. Never force-detach another session. If the lock is unavailable,
continue GitHub development without operating the console.

The existing ERP image is retained. Its application source lives in the persistent
apps volume; package metadata is in the current container environment. After a
future container recreation, rerun preflight/update to reconcile metadata before
claiming the same installed version. Production packaging/upgrade acceptance is
not established by this Test2 procedure.

## Actual Ecwid exports audited offline

The existing semicolon CSV converter and migration planner processed the supplied
October 29 exports without structural plan errors. Source hashes:

- Products: `347660a5c4ccf3d434a8beda02c63e2d137871224d2ddfbf85f8e84b27f9d2bf`.
- Orders: `bb4d515d8cb40c2ed69796617ac80ac0498f83aaebf7336340f7c2391b74804b`.

| Check | Observed result | Acceptance / action |
| --- | ---: | --- |
| Product rows / unique IDs / unique nonempty SKUs | 132 / 132 / 132 | PASS source identity/structure check |
| Enabled / disabled | 38 / 94 | Preserve disabled state; do not publish all 132 |
| Descriptions present | 132 | PASS source presence, destination parity not yet run |
| Primary image present / absent | 49 / 83 | Source omission review, not proven migration loss |
| Enabled products missing primary image | 18 of 38 | Review or supply images during iterative draft migration |
| SEO title / description present | 123 / 123 | Nine products missing each source field |
| Enabled products missing SEO title / description | 8 / 8 | Review before publication |
| Category paths | 4 | Reviewed ERP/Woo destination mapping still needed |
| Enabled tax codes | default 24, zero 14 | Explicit tax-template/class review; do not infer accounts/rates |
| Order line rows / grouped historical orders | 59 / 38 | PASS converter grouping; no financial/fulfillment replay |
| Derived customer email identities | 7 | Not a complete authoritative customer export |
| Planner structural errors | 0 | PASS conversion only; not destination acceptance |
| Variations / full galleries | Not exported | UNVERIFIED; obtain API/complete export before claiming parity |
| Store ID / currency | Not established by CSV | REVIEW; conversion audit used an explicitly unreviewed namespace |
| ERP/Woo destination parity | Not run | NOT RUN; do not report missing targets as zero discrepancies |

Raw orders/customer data and normalized plans remain private and must never be
committed to Git. No real order, including production #5IBME, was replayed. CSV
order-number and email-hash identities remain explicitly namespaced rather than
being presented as Ecwid API IDs. Current stock must come from MushroomProcess,
not from copying historical Ecwid CSV quantity values.

Remaining native gates: installed update and repeated fixture, a separate synthetic
MP ledger test database, actual authoritative stock projection, durable order/
reservation/fulfillment/financial lifecycle, and sandbox Clover evidence. Existing
restored MP and SignatureGate databases remain untouched. Ecwid retirement is no-go.

## Installed Test2 acceptance — 2026-11-01

The guarded upgrade was executed from commit
`90d672bdc791376bf6b45a269274d00ef7251597` after explicit Commerce Screen sudo
authentication. Initial preflight stopped before app mutation because flit_core
was absent. The official PyPI flit_core 3.12.0 wheel was staged on the host,
SHA256-verified, copied into ERP and installed with `--no-index --no-deps`.
Wheel SHA256: `e7a0304069ea895172e3c7bb703292e992c5d1555dd1233ab7b5621b5b69e62c`.
Private provenance receipt: `.test-deployment/private/commerce-flit-wheel.json`.
Application network isolation remained unchanged.

Upgrade result: **PASS**. Both installed module and package metadata are 0.3.1;
API SHA256 is `c6b348c56641aeba47d17cd1866a1ae65f204c6bcf3b91a3bbb70eb5f78ea91b`.
All protected record fingerprints are unchanged. No schema migration or database
restore occurred. The only restarted service was the ERP backend; its existing
image `sha256:908a38651afd93e0e2823cfee7ce4c07db02293c072f6c006d2ea26c311d3438`
was retained. Private code backup/before/after/receipt/package log:
`.test-deployment/private/commerce-upgrade-031-20261101T202024Z/`.

The installed native fixture was then executed twice, **without candidate flags**.
Both runs report installed acceptance true, module/package 0.3.1, identical API
hash, SKU `SYN-TEST2-ERP-CATALOG`, stable Woo draft product 16 and USD 12.50.
The helper verifies one ERP Item/Price, repeat import identity, and stable Woo
upserts. Canonical content stays Draft; mapping sync stays disabled. No financial
document was created. Quantity remains fixture-only, so MP inventory and the
complete order lifecycle are **not** claimed. ERP HTTP authentication is also a
separate remaining gate.

CI for that exact source commit passed:
[foundation](https://github.com/RayzorDuff/RootedOps/actions/runs/41345960247),
[recovery](https://github.com/RayzorDuff/RootedOps/actions/runs/41345960266),
[integration contracts](https://github.com/RayzorDuff/RootedOps/actions/runs/41345960282).
Local tests: 88 run, 87 passed, one PHP-dependent skip.

The full existing MushroomProcess commercial snapshot workflow already joins
`mp_ecommerce_catalog_inventory()` with `mp_commerce_inventory()` and projects
reservation-adjusted `available_quantity` as `desired_quantity`, retaining the raw
quantity as `gross_quantity`. No replacement SQL function is needed. The remaining
gate is native verification against an isolated synthetic ledger database; the
restored MP database remains untouched.
