# ERPNext bank reconciliation closeout — October 2026

This is an operational checklist, **not** a balancing-entry authorization.
Do not copy customer/account identifiers, personal transaction details, tokens,
or production Journal Entry particulars into the public repository.

## Reconciliation status and exceptions

The imported bank transactions have been reconciled for the active Dank Mushrooms
checking and savings accounts, Rooted Psyche Canvas checking and savings, former
SoFi checking, and Raymond Danks Elevations checking and withholding savings.
"All imported transactions reconciled" does **not** certify the ledger agrees
with the bank's independently reported balance.

The closeout retains these exceptions for year-end review:

- Dank Mushrooms checking: historical opening/balance-date difference of
  **$374.05**, not supported by an opening statement. Do not force a JE.
- Rooted Psyche closed SoFi account: historical incomplete-statement balance
  difference **$1,262.44**. Review deferred; no speculative entries.
- Raymond Danks Elevations checking: **$651.95** submitted Venmo payroll
  disbursement pending appearance in bank feed. When imported, match it to
  the existing submitted payment JE; do not post payroll a second time.
- Rooted Psyche Canvas BillPay checks: recorded as outgoing payments but
  not received/deposited by payees at closeout. Avoid duplicate receiving-side
  deposits before actual bank evidence.

## Stock Plaid synchronization safeguards

Stock ERPNext Sync Now in RootedOps checks enabled Bank Accounts, credentials,
legacy profile compatibility, and current Item membership before queueing jobs.
It additionally fails closed when *multiple active Bank Account records* map
to the *same Bank / Plaid account ID*. Disable the stale duplicate mapping
before synchronizing.

**Known remaining limitation:** a different Plaid Item can assign a different
Plaid account ID to the same physical bank account, and later Plaid transaction
IDs can differ after relinking. The same-Item duplicate guard does not detect
this. Until a historical fingerprint-aware importer has been implemented and
verified, do not run bulk backfill on previously reconciled overlapping mappings.
Use the read-only sync plan to review queued vs skipped accounts and verify
the identity of each real-world bank account.

### Read-only sync plan

From the ERPNext backend bench console:

```python
from rootedops_payroll.services.plaid_erpnext_compat import stock_sync_plan
plan = stock_sync_plan()
print("Eligible:", [(x["bank_account"], x["bank"]) for x in plan["candidates"]])
print("Skipped:", [(x["bank_account"], x["reason"]) for x in plan["skipped"]])
```

This makes Plaid /accounts/get calls but does not import or change transaction rows.

## Tax-payment cancellation and amendment

The Journal Entry on_cancel hook clears the **unique active tax-payment key**
when a tax-payment JE reaches cancelled docstatus. Tax type, reporting period,
and confirmation metadata remain on the cancelled JE for audit review.
The key is marked no_copy on amendments, so a replacement can claim the
canonical key without colliding with its cancelled predecessor.
Regression tests cover this behavior. Do not cancel any real tax payment JE
solely to test it.

## Temporary Frappe reconciliation scripts — verify before deletion

The conversational reconciliation used ephemeral /tmp scripts as well as
functions typed into the bench console. The public Git repository has no
access to the production backend container's /tmp files. First inventory:

```bash
cd ~/RootedOps
sudo docker compose --env-file ./.env -f docker/docker-compose.yml \
  exec erpnext-backend sh -lc \
  'find /tmp -maxdepth 1 -type f \( -name "rootedops_reconcile_*" -o -name "rootedops_*_audit_tmp.py" \) -print'
```

Review **each** listed file before removal; preserve files needed for audit
support or in-progress work. When verified as temporary and superseded:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml \
  exec erpnext-backend sh -lc \
  'find /tmp -maxdepth 1 -type f \( -name "rootedops_reconcile_*" -o -name "rootedops_*_audit_tmp.py" \) -print -delete'
```

This deletion command applies only to those /tmp naming patterns, not
application source, Bank Transactions, Journal Entries, or backup data.

## Validation and deployment

```bash
cd ~/RootedOps
git pull --ff-only origin main
git log -5 --oneline
make validate
make release-check

# Run on a dedicated test site, NEVER on production accounting data.
# Replace <erp-test-site> with the configured test site's name:
sudo docker compose --env-file ./.env -f docker/docker-compose.yml \
  exec erpnext-backend bench --site <erp-test-site> run-tests \
  --app rootedops_payroll --module rootedops_payroll.tests.test_plaid_erpnext_compat
sudo docker compose --env-file ./.env -f docker/docker-compose.yml \
  exec erpnext-backend bench --site <erp-test-site> run-tests \
  --app rootedops_payroll --module rootedops_payroll.tests.test_tax_compliance
```

Tests should run after source is deployed through the standard RootedOps
app deployment workflow. Confirm the deployed app revision matches main,
then use stock Sync Now only after reviewing the safe plan.
