# Issue #7 Phase 7 — Stock ERPNext Plaid UI compatibility

## Purpose

Make ERPNext's stock Link a new bank account and Sync Now actions safe while
RootedOps Plaid Connection Profiles coexist with ERPNext's legacy global Plaid
Settings integration.

This phase was prompted by linking Canvas Credit Union for Rooted Psyche. The
stock Link flow created the Plaid Item and Bank Accounts correctly but left the
new Bank.plaid_profile blank. A subsequent global Sync Now also attempted to
queue stale or disabled Bank Accounts whose parent Bank no longer had a Plaid
access token.

## Changes

- A Bank saved by the stock Plaid Link flow is automatically assigned to the
  enabled RootedOps profile that explicitly references the legacy ERPNext
  Plaid Settings credentials.
- Existing Bank profile assignments are never overwritten.
- ERPNext's stock enqueue_synchronization whitelisted method is overridden with
  a RootedOps compatibility wrapper.
- Global Sync Now now queues only enabled Bank Accounts with a Plaid integration
  ID whose parent Bank has an access token and an explicit legacy-backed
  RootedOps profile.
- Tokenless, unprofiled, and non-legacy-profile accounts are reported as
  skipped instead of being sent to the stock worker.

## Safety boundary

The actual queued transaction worker remains ERPNext's stock sync_transactions
implementation in this phase. That worker uses the global ERPNext Plaid
Settings credentials, so RootedOps intentionally refuses to queue Items
belonging to a non-legacy Plaid profile through this path.

Future production synchronization for independent business and personal
credential profiles should use a fully profile-aware RootedOps importer rather
than the stock global worker.

No existing Plaid access token, integration ID, Bank Account, Bank Transaction,
or reconciliation is rewritten by this deployment.

## Regression coverage

Tests cover automatic binding of a newly stock-linked Bank, preservation of an
existing profile assignment, filtering of unsafe Items, and queueing only the
safe candidate set.
