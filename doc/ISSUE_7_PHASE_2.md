# Issue #7 — Plaid Connection Profiles — Phase 2

## Scope

Phase 2 establishes the relationship between ERPNext's existing Plaid Item
representation and a RootedOps Plaid Connection Profile.

In the current ERPNext integration, the local Plaid Item is represented by the
`Bank` record carrying the `plaid_access_token`. Phase 2 adds:

```text
Bank / Plaid Item
    |
    +-- plaid_profile -> RootedOps Plaid Connection Profile
```

The ERPNext Bank Account remains responsible for accounting placement.

## Production safety

This phase deliberately does **not** change the existing Plaid API client,
Link/Hosted Link, transaction synchronization, webhook handling, or historical
import implementation.

It does not:

- recreate Plaid Items;
- replace access tokens;
- call Plaid during migration;
- reset transaction synchronization state;
- create Bank Accounts;
- create Bank Transactions;
- change accounting mappings;
- introduce a second live credential set.

## Custom field

A `plaid_profile` Link field is created on `Bank`, pointing to
`RootedOps Plaid Connection Profile`.

The field is read-only in the ERPNext UI. Profile assignment is performed by
controlled server-side migration logic rather than by silently changing an
existing Item's credential context.

## Legacy migration

The migration is intentionally explicit rather than an automatic part of
`bench migrate`.

Before migration, `snapshot_plaid_item_state()` records safe fingerprints and
counts for the connected Plaid Items. The complete local Item state is hashed,
so access tokens and synchronization fields can be compared without exposing
their values.

`migrate_existing_plaid_items(profile_name)` then:

1. resolves the explicitly supplied profile;
2. finds every connected ERPNext `Bank` record with a Plaid access token;
3. assigns the profile only where `plaid_profile` is currently blank;
4. leaves already-profiled Items unchanged;
5. never calls Plaid;
6. never changes `plaid_access_token` or any other Item state;
7. verifies Item fingerprints, Item count, Bank Account counts, and Bank
   Transaction counts before committing.

The migration is therefore idempotent.

## Verification

The production operator should capture the pre-migration snapshot, perform the
migration against the intended default profile, and retain the returned
verification result.

The verification must show:

```text
same Plaid Item count
same Plaid Item names
same Item state fingerprints
all Items have a profile
same Bank Account mappings/counts
same Bank Transaction counts
```

No raw access token, credential, or synchronization-state value is printed.

## Next phase

Phase 3 can refactor Plaid API credential selection so that calls for an
existing Item resolve the Item's assigned profile rather than implicitly using
the global ERPNext `Plaid Settings` credentials.
