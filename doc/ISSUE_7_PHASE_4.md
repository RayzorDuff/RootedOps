# Issue #7 Phase 4 — Profile-bound Link / Item lifecycle

Phase 4 carries the selected Plaid Connection Profile through creation of a new Plaid Link session and completion of a new/unlinked ERPNext Bank connection.

## Scope

- Create Link tokens only from an explicit profile.
- Exchange the public token using that same profile.
- Verify the returned Plaid Item using the same profile.
- Fetch accounts using the same profile.
- Bind the resulting access token and profile to a new/unlinked ERPNext `Bank` record.
- Refuse to overwrite an existing Plaid access token or silently change an existing profile.

## Safety boundary

This phase does not relink existing production Items. Existing Items remain bound to their current credential context, including `legacy-current`.

The bind operation is intentionally limited to a Bank record without an existing Plaid access token/profile. Moving an existing Item between profiles remains a separate controlled relink/migration operation.

## API

Internal service:

- `create_link_token(profile_name, ...)`
- `exchange_public_token(profile_name, public_token)`
- `bind_exchanged_item(bank_name, profile_name, public_token)`

Whitelisted API:

- `rootedops_payroll.api.plaid_link.create_profile_link_token`

The whitelisted operation requires the caller to supply the profile explicitly; it does not fall back to the default profile.

## Not included

- automatic Bank Account mapping;
- automatic company selection;
- existing Item relinking;
- webhook processing;
- scheduled transaction synchronization.

Those remain subsequent Issue #7 work.
