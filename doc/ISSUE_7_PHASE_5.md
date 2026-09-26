# Issue #7 Phase 5 — Profile-aware read-only Item sync verification

Phase 5 adds a safe operational boundary for existing Plaid Items: RootedOps can verify Item health and call `/transactions/sync` using the credential profile assigned to that Item.

## Scope

- resolve the Plaid client from the Item's explicit `plaid_profile`;
- retrieve Item status using that profile;
- perform a read-only `/transactions/sync` request using that same profile;
- optionally forward an operator-supplied cursor without persisting it;
- return only safe metadata and transaction counts;
- provide a whitelisted verification endpoint;
- add tests for independent profile routing and cursor handling.

## Explicit non-scope

Phase 5 does **not**:

- persist a transaction cursor;
- create or modify ERPNext Bank Transactions;
- change Bank Account mappings;
- alter an existing Plaid Item or access token;
- create a new Plaid Item;
- remove an Item;
- implement production transaction import.

Production synchronization/import and cursor persistence remain a separate phase so that the existing three production Items can be verified without changing accounting data.

## Safety

The verification response does not contain access tokens, cursor values, or transaction contents. It reports only fingerprints, profile identity, Item/institution metadata, counts, and whether more data is available.
