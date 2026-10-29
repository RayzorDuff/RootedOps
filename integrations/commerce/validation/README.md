# Supplemental offline database validation

This optional harness restores a PostgreSQL plain SQL gzip dump into a fresh
PGlite sandbox, using the pinned PostgreSQL 18 WASM runtime. It verifies each
COPY block's row count, restores remaining constraints/indexes/functions, applies
migration 051 and writes a private inventory snapshot. It refuses existing data
directories. Source records are never fixtures or repository contents.

```bash
npm ci
node restore_dump.mjs /private/backup.sql.gz /private/new-pglite-data /private/results /path/to/MushroomProcess/schema/pgsql/051_erp_commerce_catalog.sql
```

This is supplemental validation, **not** a claim of native PostgreSQL 16 Docker
restore compatibility, a live ERP migration, or a WooCommerce API test. The native
staging restore and live round-trip acceptance tests remain required.
