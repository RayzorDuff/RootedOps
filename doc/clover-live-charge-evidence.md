# Production Clover charge evidence

The observed live Ecommerce GET response omitted `object`, `livemode`, and
`amount_refunded`, and returned `captured: false` with a full `amount_captured`.
Do not manufacture missing provider fields or treat the dashboard note as an
API capture proof.

The production adapter can additionally read the exact merchant payment using
`CLOVER_LIVE_PLATFORM_TOKEN` in the private order-worker environment. Reuse the
existing n8n `CLOVER_ACCESS_TOKEN` privately; never put it in source, receiver
configuration, command arguments, logs, or this document.

Both authenticated GET records must match the payment ID, Woo display number,
Clover order ID, and full amount. The merchant response must report online
SUCCESS, card transaction AUTH/CLOSED, and an explicitly expanded empty refunds
list. Pending, PREAUTH, voided, refunded, missing, or mismatched records stop
posting. Explicit conflicting Ecommerce merchant/environment fields still fail.
Missing refund amounts are interpreted as zero only after this corroboration.
The resulting signed packet records the corroboration method, not card details.

The ordinary sandbox path remains strict and unchanged. ERP still requires the
individual order and exact charge approval, a submitted matching Sales Order,
and the company clearing account. Existing reconciliation creates the stock-
neutral invoice/receipt idempotently and confirms the MP reservation. This
change neither captures payments nor publishes stock nor dispatches products.

References:
- https://docs.clover.com/dev/docs/get-a-charge
- https://docs.clover.com/dev/docs/making-a-sale
- https://docs.clover.com/dev/docs/permissions

Validation: `python3 -m unittest discover -s tests -p 'test_commerce*.py'`.
Hosted acceptance must still confirm the actual invoice, payment, and MP links.
