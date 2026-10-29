# Issue #7 Phase 6 — Profile-Aware Historical Plaid Backfill

## Purpose

Make the existing controlled historical Plaid backfill explicitly aware of the Plaid Connection Profile assigned to the canonical ERPNext Plaid Item.

The existing `BACKFILL_PROFILES` remain historical-import recipes. They are not credential profiles. The actual credential context is resolved from the target Bank/Plaid Item and is pinned to the staging session.

## Safety

- No Plaid access token is replaced.
- No production Plaid Item is recreated.
- No transaction cursor is persisted or changed.
- No Bank Account or Bank Transaction is written by staging/inspection.
- Import receipts contain profile names and fingerprints only.
- A session refuses to continue if the canonical Item's assigned Plaid Connection Profile changes.

## Operator-visible distinction

`profile` identifies the historical backfill recipe, such as `high_plains_2026`.

`plaid_connection_profile` identifies the actual Plaid credential context, such as `legacy-current`.

This distinction prevents a historical recipe name from being mistaken for a Plaid credential context.

## Verification

Phase 6 is complete when the targeted historical-import tests pass and the existing Phase 5 production read-only verification remains unchanged. No production historical import should be run merely to deploy this phase.
