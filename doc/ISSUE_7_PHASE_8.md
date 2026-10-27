# Issue #7 — Separate Plaid Item Link for the same institution

## Intent
Allow an operator to link a second authenticated Plaid Item using an existing credential profile, without replacing an earlier Item for that institution.

## ERPNext operator workflow
1. In ERPNext create a **distinct Bank record** for the second Item, using a name that distinguishes this connection from the original. Do not give the record an access token or an assigned profile.
2. Open **Plaid Settings**. Under the **Plaid** menu choose **Link Separate Plaid Item**.
3. Select the existing credential profile and the new, unconnected Bank record.
4. Authenticate in Plaid Link using the independent login. After Plaid returns a public token, the browser sends it to a permission-protected POST endpoint.
5. The server exchanges the public token and persists the resulting access token/profile to **only** the selected unconnected Bank. It refuses to replace any previously configured Item or profile.
6. Review the account list for the new Item. The Link flow deliberately does **not** create Bank Accounts, GL accounts, Bank Transactions, import jobs, or sync cursors.
7. Manually map only the newly required real-world accounts to the correct ERPNext company/GL. When accounts appear under two Plaid Items, designate only one account mapping as active for transaction imports.

## Constraints and security
- Keep the existing Item and its associated Bank Accounts unchanged; do not reconnect the original Item to the different login.
- Use the existing RootedOps Plaid Connection Profile; a separate banking login does not require a separate set of Plaid API credentials.
- Only administrators authorized to write Plaid Connection Profiles and the selected Bank may complete a new link.
- Token exchange remains server-side and the result provides only fingerprints, masks and account display names.
- Browser Link token/public token must not be printed to console, included in public issues, or persisted in client storage.
- No automatic account mapping or backfill occurs, especially for accounts shared between logins.
- For stock ERPNext **Sync Now**, only active, profile-compatible, token-backed account mappings are eligible; avoid running sync until duplicate account mappings have been evaluated.
- To switch payroll's withholding reserve destination, map the new real-world bank account to a new Bank-type GL account, then configure the Company's explicit withholding-bank GL selector. Keep prior account/ledger history for reconciliation.

## Verification
Run the Plaid Link unit tests and RootedOps validation before deployment. After Link, inspect Bank names, profile membership, token-presence booleans and safe Plaid account metadata; never output access tokens.

## Deployment
```bash
cd ~/RootedOps
git pull --ff-only origin main
sudo docker cp erpnext/apps/rootedops_payroll/rootedops_payroll/api/plaid_link.py erpnext-backend:/home/frappe/frappe-bench/apps/rootedops_payroll/rootedops_payroll/api/plaid_link.py
sudo docker cp erpnext/apps/rootedops_payroll/rootedops_payroll/public/js/plaid_separate_item.js erpnext-backend:/home/frappe/frappe-bench/apps/rootedops_payroll/rootedops_payroll/public/js/plaid_separate_item.js
sudo docker cp erpnext/apps/rootedops_payroll/rootedops_payroll/hooks.py erpnext-backend:/home/frappe/frappe-bench/apps/rootedops_payroll/rootedops_payroll/hooks.py
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend bench --site erp.danks.store clear-cache
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend bench build --app rootedops_payroll
sudo docker compose --env-file ./.env -f docker/docker-compose.yml restart erpnext-backend erpnext-frontend
```

## Phase 9 — Fail-closed sync checks

Before submitting ERPNext stock Plaid sync jobs, RootedOps calls `/accounts/get` using the current Item token and checks that each active Bank Account's integration ID is present. The result is cached by Bank within each planning pass. Missing IDs and failed API lookups fail closed and are reported as skipped without exposing tokens or account IDs. This guard does not rewrite bank mappings, change account ownership, remove duplicate transactions, restore a personal login, or settle payments. Run the updated unit tests before using Sync Now. Continue suspending synchronization on the overlapping account mappings until they have been corrected.
