# RootedOps 1.5.36

Production Clover reconciliation now supports the observed Ecommerce response
using a second authenticated merchant payment read. Matching SUCCESS/AUTH/CLOSED
and explicit no-refund evidence are required; missing metadata alone never
confirms a payment. Sandbox behavior and ERP approval gates remain unchanged.

Configure `CLOVER_LIVE_PLATFORM_TOKEN` privately from the existing n8n production
connection. No Clover payment mutation endpoints are added. See
`doc/clover-live-charge-evidence.md`. Phase patch; no Git tag.
