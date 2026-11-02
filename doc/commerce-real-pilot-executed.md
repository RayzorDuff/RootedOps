# Test2 real Ecwid pilot: executed checkpoint

This is new test2 evidence, separate from deleted-Linode history and synthetic
catalog/ledger predecessor tests. RootedOps host checkout:
`f46f7af2067bdd65f2a8fd2748920061ad8a1148`; installed commerce 0.3.1.
Repository continuation main `1183f10416f41c39ce0c81971161d36a3addec24`
includes PRs #48/#49; no host checkout update or image rebuild was needed.

## Verified destination coverage

Three real ERP Items, Commercial Product Content records and disabled Ecwid
channel mappings were imported through installed `rootedops_commerce.api.import_product`.
Each import ran twice with identical returned identities. Native catalog read-back
asserted exact source key/payload, public title, descriptions and both SEO fields,
Draft content state and disabled mappings.

| Ecwid product ID | ERP Item / original SKU | Source price (USD confirmed by user) |
| --- | --- | --- |
| 610274980 | M5P9B1D6Q8R2S | 14.95 |
| 610274742 | cdbd6f64-2637-488c-b9fc-0a5a47bb7322 | 9.95 |
| 711334880 | E3ZY47P9K64TT | 9.95 |

Source key format: `ecwid:95802503:product:<product ID>`. Store namespace 95802503
comes from the original exported image paths; independent profile verification
remains pending. The immutable source rows retain all original CSV fields,
including price, quantity, tax code, category, URL and UPC.

Three real images were archived and uploaded as ERP Files. Receipt checksums:

| Product | SHA-256 | Bytes |
| --- | --- | --- |
| Grow kit | 963642a355e762098d19525d47d2045f1de8d5586e4dad1abda5a7c23d9e6ee9 | 83924 |
| LC syringe | f4a2b4da373a52fedfac7442cfe238c070ed7e85db86fb918c06952c7466eebd | 1926513 |
| Freeze dried | 38c998b4b37dc29ffee93597e3c01f5f258ba792edcd97469cb0e7c2a7fb0896 | 120418 |

The native transaction required maintenance mode, paused scheduler, no enabled
outgoing email accounts/webhooks/notifications and no sales/financial documents.
No restored MP or SignatureGate database, shared service configuration or production
system was modified. Existing host receipt showed cron, HTTP and mail blocked and
zero payment gateways; no attempt was made to enable them.

## Verified WooCommerce pilot

The browser environment briefly disappeared, then recovered. The previously submitted
command's completed output was observed: all three products passed exact SKU/source
identity, draft state, zero managed stock, description, short-description, image ID
and both SEO metadata comparisons. Each product was upserted twice with the same ID.
The LC syringe is Woo product 20 / media 19; freeze-dried product 22 / media 21.
Read the private receipt for the complete three-product ID map.

Products remain Draft and hidden. Source prices and tax codes are archived in
metadata; no sellable price or ERP Item Price has yet been assigned. The user
confirmed USD during this session. A subsequent price-import attempt was refused
by sudo before its Python body executed, so no price writes occurred. Apply the
confirmed USD rates next, preserving disabled publication/payment controls.
Tax mappings and actual variation definitions remain unresolved.

## Private host evidence and resumption

Directory:
`/home/rootedops/RootedOps/.test-deployment/private/ecwid-pilot/`

- `source-rows.json`: three complete original CSV rows.
- `source.json`, `plan.json`: selected source and existing planner output.
- `media/manifest.json` and checksum blobs: three archived originals.
- `erp-import.py`, `erp-receipt.json`: executed native child script and verified
  ERP identities/file URLs. Child script expects product records with verified
  media metadata and base64 blobs on stdin; do not invoke without that input.
- `woo-import.py`: submitted import/reconciliation script.
- `woo-media-receipt.json`, `woo-receipt.json`: inspect if present. A pending media
  record without an ID requires checksum-filename reconciliation before retry.
  A missing final receipt does not prove no remote writes occurred.

First acquire the normal Commerce console lock, attach only Commerce Screen and
check the command has returned. Read the private receipts and inspect exact Woo
SKUs/source metadata before any replay. Match attachments by checksum filename.
Once all pending uploads are reconciled, the stored script can be repeated:

```bash
sudo -n python3 /home/rootedops/RootedOps/.test-deployment/private/ecwid-pilot/woo-import.py
```

This repeats content-only draft projection; it does not add confirmed USD prices.
Add reviewed prices through existing installed ERP import/compiler and Woo channel
adapter. Do not overwrite the immutable source payload to clear a discrepancy.
Verify two destination reads/imports keep IDs and counts stable, then expand by
complete source product family using PR #50.

## Access interruption and lock

Commerce acquired the exclusive lock and used Screen 2446552.commerce.
After the environment interruption, completed Woo output was recovered.
The console subsequently returned to the locking shell; sudo refused the price
import before execution. The locking shell was explicitly exited and the outer
rootedops prompt observed, verifying release. Do not remove lock files or terminate
another session.

## Remaining gates

- Persist and reconcile three confirmed USD Item Prices and Woo prices.
- Review source default/zero tax mappings, categories and actual variations;
  CSV lacks complete combinations/gallery definitions.
- Profile/store identity verification; public storefront read returned HTTPError.
- Expand draft catalog incrementally after complete pilot reconciliation.
- Installed order → MP → ERP proof, financial reconciliation and Clover sandbox.
- No Ecwid retirement/publication/cutover recommendation.
