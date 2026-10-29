# Issue #7 — Plaid Connection Profiles — Phase 3

## Scope

Phase 3 makes Plaid API credential selection profile-aware. A Plaid API client
is resolved from the RootedOps Plaid Connection Profile assigned to the local
Plaid Item (`Bank`), rather than from the global ERPNext `Plaid Settings`.

The core rule is:

```text
Plaid Item -> Plaid Connection Profile -> API credentials
```

ERPNext Bank Account and Bank Transaction mappings remain unchanged and remain
the accounting authority.

## Centralized client

`services/plaid_client.py` provides:

- `get_plaid_client(profile_name)`;
- `get_plaid_client_for_item(bank_name)`;
- `get_plaid_client_for_bank(bank_name)`.

The client resolves credentials through `plaid_profile.py` and keeps the raw
client ID and secret internal to the server-side client object. Callers do not
select environment variable names or read `Plaid Settings` directly.

The client includes the resolved profile in request failures while omitting
credential values. Its credential fields are excluded from its representation.

## Historical import

The existing controlled historical backfill now resolves its Plaid client from
the target ERPNext Bank/Plaid Item's assigned profile. This applies to:

- live Item health checks;
- Hosted Link creation and status;
- public-token exchange;
- temporary candidate Item inspection;
- account retrieval;
- transaction readiness and historical retrieval;
- candidate Item cleanup.

A historical backfill therefore cannot silently use the global legacy Plaid
credentials once the target Item has an explicit profile.

## Compatibility

The current `legacy-current` profile continues to resolve the existing ERPNext
`Plaid Settings` credentials through explicit legacy references. This preserves
the current production credential context while Phase 3 changes the routing
point. No access tokens, Items, cursors, Bank Accounts, or Bank Transactions are
rewritten by this phase.

## Explicit non-goals

Phase 3 does not:

- create a second live credential profile;
- relink an existing Item to another credential context;
- recreate or replace Plaid Items or access tokens;
- reset transaction cursors;
- change accounting-company mappings;
- implement the Link/Hosted Link administrative profile-selection UI;
- change ordinary transaction synchronization outside the Plaid code present in
  this RootedOps application tree.

## Tests

Automated tests cover:

- profile-specific client resolution;
- Item-to-profile client resolution;
- disabled/missing profile failures;
- independent clients for different profiles;
- credential values excluded from client representations;
- profile-bound API error messages without credential disclosure.
