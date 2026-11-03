# Recurring MushroomProcess → Woo draft inventory — guarded host adapter

Status: proposed opt-in single-writer implementation. The **one-time** seven-product
projection is already complete; **do not** re-run it. All 24 MP↔ERP↔Woo exact
identities, 24 independent physical pools and the staging Woo REST key are
accepted. Existing Ecwid hourly publication remains active.

## Ownership and writer exclusivity

MushroomProcess remains the physical stock/reservation authority. The adapter
queries `mp_ecommerce_catalog_inventory()` + `mp_commerce_inventory()`
fresh for each execution and before each planned PUT. It checks the approved
24-row manifest, old private Woo identity receipt, exact remote product ID,
original Ecwid source marker, SKU, hidden/draft/simple status, `manage_stock`,
and expected previously acknowledged stock before a quantity-only PUT.

The host adapter uses an exclusive OS `flock` plus SQLite `projection` and
`attempts` records with WAL, `synchronous=FULL`, monotonic **local**
acknowledged sequence, pending-before-PUT journal, verified read-back and
failure refusal. It will **never auto-retry an unknown network outcome**.
It is not a database-global MP source revision; it assumes this is the
**only Woo stock writer**, and it re-reads the full MP snapshot before PUT.
It cannot make an external Woo PUT and MP reservation atomic.

Never turn on the existing n8n Woo branch in parallel. Leave
`MP_SYNC_WOO_ENABLED=false`. The separate, default-off gate
`MP_WOO_RECURRING_CLI_ENABLED=false` controls only this host adapter.
Do not activate public checkout or create ERP Stock Ledger/Bin changes.

## Preflight and offline regression

After reviewing/merging this PR, on the **production RootedOps host**:

```bash
cd ~/RootedOps
git pull --ff-only origin main
python3 -m py_compile scripts/commerce_woo_recurring.py
python3 -m unittest discover -s tests -p 'test_commerce_woo_recurring.py' -v
sudo -n docker inspect mushroomprocess-bridge-postgres >/dev/null
sudo -n docker inspect dank-store-test-dank-wordpress-1 >/dev/null
```

Back up the **private inventory receipt and state**, WordPress DB and MP
PostgreSQL DB. Confirm private `.env` is mode 0600 and the separate REST
key exists, but never print `MP_SYNC_WOO_AUTHORIZATION` or copy it into
Cron/systemd service files. Keep the host private receipts under
`~/commerce-migration/inventory-private` (0700), with SQLite and `-wal/-shm`
kept together in backups.

```bash
# Safe, one-time baseline: all 24 remote Woo stocks must ALREADY equal MP.
# This creates the *state database only*, not stock writes.
python3 scripts/commerce_woo_recurring.py bootstrap

# Repeatable read-only drift evaluation, even while the write gate is off.
python3 scripts/commerce_woo_recurring.py check
```

Both must pass (0 pending changes immediately after the accepted initial
projection). Otherwise STOP: inspect recent MP changes and Woo before
allowing recurring writes. Bootstrap is intentionally non-repeatable.

## Explicit gated application and scheduling

Once the baseline and offline regression pass, add exactly
`MP_WOO_RECURRING_CLI_ENABLED=true` to the existing private host `.env`,
without changing `MP_SYNC_WOO_ENABLED=false`. This new key exists in
`.env.example` but must be added to the existing host `.env` manually.
Do not overwrite unrelated settings or reinitialize the state DB.

```bash
# After enabling the separate gate, this is the controlled first update.
python3 scripts/commerce_woo_recurring.py apply
# Confirm subsequent run is an idempotent no-op.
python3 scripts/commerce_woo_recurring.py check
```

If the first apply is accepted, the preferred schedule is one **single**
operator-managed process every 15 minutes under the existing unprivileged
`dankmushrooms` account. Configure the scheduler only after confirming
that noninteractive `sudo -n docker` works and that no other Woo inventory
writer is active. Example operator crontab entry (review host paths first):

```cron
*/15 * * * * cd /home/dankmushrooms/RootedOps && /usr/bin/python3 scripts/commerce_woo_recurring.py apply >> /home/dankmushrooms/commerce-migration/inventory-private/woo-recurring.log 2>&1
```

Use `crontab -e` to add one entry; do not paste a command that replaces
the whole crontab. Cron is *not* installed or modified by this PR.
If using the workflow-based n8n adapter later, stop/remove the host
schedule and set `MP_WOO_RECURRING_CLI_ENABLED=false` **before**
enabling that adapter. Never enable two writers simultaneously.

## Failure and rollback

A pending/failed `attempts` row blocks **all future runs**. Do not blindly
delete records or re-bootstrap. Run:

```bash
python3 scripts/commerce_woo_recurring.py reconcile
```

This sends **no Woo PUT**. It may finalize the ACK only when the current
fresh MP snapshot, product ownership and Woo quantity match the pending
target; otherwise it stops for manual intervention. If Woo still has the
pre-write quantity or source has moved, investigate the unknown network
result and authorize a targeted recovery, not a replay of the original
potentially successful PUT. Preserve state and original receipt.

To disable immediately, set `MP_WOO_RECURRING_CLI_ENABLED=false` and
remove/disable the schedule; `MP_SYNC_WOO_ENABLED=false` remains.
Do not roll back Woo stock to the old zero values; resynchronization must
use a fresh MP-authoritative snapshot.

## Acceptance before public cutover

Exercise: no-op replay; increase/decrease on a reviewed hidden draft;
reservation/cancel/partial shipment; an expired/consumed/moved physical
product; concurrent invocation refused; changed Woo stock fails closed;
source changes between snapshot and PUT refused; HTTP timeout after PUT
blocks replay until recovery; key revocation/auth failure; database loss
and backup/restore of local state. Preserve per-run private evidence.

**Remaining launch blockers**: the local sequence is not an MP-native
monotonic event stream; cross-provider payment/order reservation ingestion,
Woo webhook replay, ERP operational availability projection, Ecwid/Woo
dual-checkout arbitration and exact merchant payment acceptance remain
separately gated. Until resolved, Woo stays hidden drafts and Ecwid stays
live, independent of whether this staging-only recurring writer is active.
