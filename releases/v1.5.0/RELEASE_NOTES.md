# RootedOps v1.5.0 — Issue #7 Phase 4

## Profile-bound Plaid Link lifecycle

Phase 4 carries an explicitly selected Plaid Connection Profile through new Link-token creation, public-token exchange, Item verification, and account retrieval.

A new/unlinked ERPNext Bank may be bound to the selected profile. Existing Plaid Items cannot be silently overwritten or moved between credential contexts.

Existing production Items remain on `legacy-current` until a controlled relink/migration process is implemented.
