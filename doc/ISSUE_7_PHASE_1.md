# Issue #7 — Plaid Connection Profiles — Phase 1

## Scope

Phase 1 establishes the generic **Plaid Connection Profile** configuration
boundary. It does not migrate or modify any existing production Plaid Item.

The architectural rule is:

```text
Plaid Connection Profile
    |
    +-- Plaid credential context

Plaid Item
    |
    +-- later: exactly one Plaid Connection Profile

ERPNext Bank Account
    |
    +-- accounting placement remains authoritative
```

This preserves the Issue #7 separation between external Plaid API identity and
ERPNext accounting identity.

## New DocType

`RootedOps Plaid Connection Profile`

Fields:

- `profile_name` — stable machine identifier;
- `display_name` — operator-facing name;
- `enabled` — permits credential resolution for the profile;
- `is_default` — identifies the future migration/default profile;
- `environment` — `sandbox`, `development`, or `production`;
- `client_id_secret_ref` — protected configuration-key reference;
- `secret_secret_ref` — protected configuration-key reference;
- `description` — optional administrative description.

Raw Plaid credentials are intentionally absent from the DocType.

## Credential resolution

`rootedops_payroll.services.plaid_profile` provides the first centralized
credential-resolution boundary.

A profile's credential references are resolved server-side from Frappe/site
configuration first and environment variables second. The service produces
the Plaid base URL from the selected environment.

Profile status is safe for operator-facing diagnostics: it reports whether
credential references exist and resolve, but never returns the client ID or
secret value.

## Validation

Enabled profiles must have both credential references and both references must
resolve to non-empty protected configuration values.

Disabled profiles may remain incomplete so configuration can be staged before
credentials are available.

Profile names are deliberately generic and may represent contexts such as:

```text
business
personal
rooted_psyche
rental_property
```

The implementation does not hard-code those names.

Only one profile may be marked as the default.

## Production safety

This phase intentionally does **not**:

- alter ERPNext `Plaid Settings`;
- alter an existing Plaid Item or access token;
- add a profile field to an existing Item;
- migrate existing Items;
- change transaction synchronization;
- change historical import;
- change webhooks;
- change Link/Hosted Link behavior;
- create a second live credential set.

The existing global Plaid integration therefore remains the production source
of truth until the later migration phase is explicitly deployed and verified.

## Verification required before Phase 2

Before assigning existing Items to profiles, verify in the deployed
environment that:

1. the new DocType migrates successfully;
2. a disabled/incomplete profile can be saved;
3. an enabled profile refuses unresolved credential references;
4. profile status does not expose credential values;
5. the existing Plaid Item count is unchanged;
6. existing access tokens and transaction cursors are unchanged;
7. existing Bank Account mappings and Bank Transaction counts are unchanged;
8. existing Plaid historical-import functionality remains operational.
