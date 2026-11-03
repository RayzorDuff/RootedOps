# ERPNext Item commercial-content editor (candidate)

Relates to RootedOps #2 and migration #20. This feature keeps the existing
**Commercial Product Content** DocType as the authoritative editorial record.
It exposes that content on ERPNext's standard **Item** form, with no duplicate
editable Item metadata or WooCommerce writes.

## Item screen

After an app migration, a namespaced **Commerce Content** section is created
on Item, immediately after the native Description field. The preview shows:
public title, short and full descriptions, SEO title and description,
publication status, source identity, gallery media/alt text, and channel
override identities/titles. All values are escaped for safe Desk display.

The **Commerce** button group provides:
- **Edit Commerce Content** (where Item and Commerce Content write permissions
  permit): a dialog for title, short/full descriptions and SEO title/description,
  saved directly to the canonical Commercial Product Content record.
- **Open Full Commerce Record**: the normal ERPNext Commerce form, for full
  gallery, alt text, per-provider overrides and publication-status editing.

The canonical DocType's `on_update` maintains native Item name/description
when these editorial fields change through *either* ERP interface. It refuses
native Item drift instead of overwriting an independent edit. The dialog
uses a content modified-timestamp concurrency check, field allowlist and
permissions on **both** Item and Commerce Content.

**Important:** Saving product content in ERPNext does **not** publish the
product, turn on Woo mappings, change stock/prices/taxes, or immediately
change WooCommerce. The separate staged ERP-to-Woo projection must first
receive read-only parity, ownership and replay acceptance (#2/#20).
Until then, editable content is authoritative in ERP but outbound channel
changes remain pending. Do not manually copy Woo values back into ERP.

## Deployment and acceptance

This is candidate code requiring an isolated test2 browser test before
production deployment. It does not change data during installation, except
adding two namespaced Item custom metadata fields. No app-specific
`Item` database columns store duplicate SEO or gallery values.

After review/merge and a verified, scoped deployment to test2:
1. Open a migrated Item. Confirm the preview shows title, descriptions, SEO,
   publication status, gallery and override summaries.
2. Open the editor as Sales Manager; change one synthetic Item's SEO title,
   description and public title. Save; confirm content and native
   Item.item_name/description match and a repeated edit is idempotent.
3. Open Full Commerce Record; edit gallery/alt text and a provider override;
   confirm they remain visible on the Item preview after refresh.
4. Open as Sales User; verify preview but no edit controls. Try direct endpoint
   write without permission and confirm rejection.
5. Open concurrent editor sessions and verify stale modified timestamps are
   rejected. Attempt a direct native Item description/title edit and confirm it
   is refused; deliberately diverge a disposable test record to verify the
   Commerce editor also refuses overwriting an independent edit.
6. Verify source_payload, Item Price, tax templates, inventory, publication
   state, Woo products and financial record counts remain unchanged.
7. Verify both forms in Frappe v16 and that static assets load after migrate.

Do **not** test with real production Item edits until test2 UI acceptance.
The 132 canonical descriptions were already reconciled and verified zero
native Item differences on 2026-11-03. Preserve that acceptance.
