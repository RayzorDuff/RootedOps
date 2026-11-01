# Durable order lifecycle rehearsal

This is native disposable-PostgreSQL contract evidence, separate from the installed
test2 ERP catalog evidence in `commerce-installed-031.md`. It does not create a
WooCommerce REST order, submit ERP financial documents or contact Clover.

The integration workflow pins MushroomProcess main commit
`451393c621b64c5bd4ca7d03b1525c6253f641ae`, retaining the production-equivalent
reconciliation and current reservation/partial-shipment interfaces. It applies the
ordered `schema/pgsql/0*.sql` migrations only to a fresh CI `commerce_test` database.
Never run this fixture suite against a restored test2 database: its per-test cleanup
deletes commerce ledger rows. The runtime restricts database names and local hosts;
the suite additionally refuses existing products, lots or commerce orders.

## Assertions

- Raw-body authenticated Woo payloads created directly in `processing` enter the
  durable inbox and reserve stock; no preceding unpaid event is required.
- Existing `pending` intake still reserves stock. Duplicate delivery creates no
  additional order/reservation, and cancellation releases unshipped holds.
- Channel stock uses the existing join between `mp_ecommerce_catalog_inventory()`
  and `mp_commerce_inventory()`, subtracting reservations exactly once.
- A two-unit order reserves both units. Shipment acknowledgment refuses a product
  before an explicit synthetic operator movement to Shipped. One-unit acknowledgment
  is partial and repeat acknowledgment is duplicate. Refresh does not re-reserve the
  shipped unit. Cancellation releases the remaining hold and preserves shipment
  history and physical location.
- ERP references and capture evidence in these tests are deliberately mocked.
  They prove SQL identity/guard integration, not ERP posting or Clover validation.
- Existing concurrent receipt, lost ERP response, dead-letter replay, lease fencing
  and financial-reference refresh tests remain in the same suite.

## Reproduce in an empty disposable database

Install PostgreSQL 16 and Python `psycopg[binary]==3.3.6`; create an empty local
`commerce_test` database and export its synthetic-only PG credentials. Check out
MushroomProcess at the pinned commit above, then:

```bash
export COMMERCE_STAGING_ONLY=1
export COMMERCE_INBOX_DSN='postgresql://commerce_test:synthetic-only@localhost:5432/commerce_test'
for file in /path/to/MushroomProcess/schema/pgsql/0*.sql; do
  psql -v ON_ERROR_STOP=1 -f "$file" || exit 1
done
python integrations/commerce/test_inbox_postgres.py -v
```

Do not pass production credentials or a shared restored database. GitHub Actions
creates its own database and synthetic credentials automatically. Browser checkout,
automatic Woo webhook emission, installed ERP HTTP authentication, submitted
financial document reconciliation, actual Ecwid parity and Clover sandbox remain
separate staging acceptance gates.
