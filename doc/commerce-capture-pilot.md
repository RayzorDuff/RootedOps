# Verified Clover sandbox capture

Run this after the Woo order receipt has completed on both staging targets.
Use the official plugin's Woo transaction ID as the candidate Clover Ecommerce
charge ID. Match it against the authenticated sandbox GET, the display order
number in the signed Woo receipt, explicit sandbox mode, the reviewed merchant
credential, exact currency and amount. If the response includes `merchant_id`,
it must match the configured merchant. Independently verify the sandbox key's
merchant association in the merchant portal. Charge lookup reveals no trusted
bank deposit or actual processing fee in this workflow.

On the separate staging ERP site, set `commerce_clover_capture_pilot` with
`enabled: true`, `merchant_id`, `company`, `clearing_account` and a private
`evidence_hmac` shared only with the worker. Use a staging Accounts Manager or
System Manager token. Keep the production ERP order and payment flags off.
Configure the pilot Woo site with `clover_capture_pilot: true` and an explicit
`clover_payments: clover` gateway mapping. Dedicated disposable tax, Item and
customer mappings still apply. Review and submit the synthetic Sales Order
in ERP before running the capture step.

Set the sandbox private key, merchant ID and proof key privately in
`CLOVER_SANDBOX_PRIVATE_KEY`, `CLOVER_SANDBOX_MERCHANT_ID` and
`COMMERCE_CAPTURE_EVIDENCE_KEY`. Run the existing staging order worker until the
latest payment-related Woo event is done. Then run:

```bash
python integrations/commerce/runtime.py reconcile-capture \
  --config "$ORDER_INBOX_CONFIG" --order-key woocommerce shop-test.danks.store "$WOO_ORDER_ID" \
  --posting-date "$REVIEWED_POSTING_DATE"
```

Expect `confirmed` with the Sales Order, Sales Invoice and Payment Entry IDs.
The invoice has stock posting off. The receipt debits Clover clearing for the
gross capture and allocates the customer receivable. Native ERP documents, the
merchant/capture uniqueness record, and both ERP references commit as one
transaction. The same command recovers a lost ERP response and retries MP
linking/confirmation. It cannot post to a production ERP hostname. A pending
Woo snapshot returns `awaiting_paid_woo_snapshot`; a failed or contradictory
Clover response stops processing. A matched refund returns `refund_review`
without posting refunds, restocking, or confirming the hold. A manually linked
invoice/receipt pair must already validate against the order and existing
processor receipt/clearing account before it can be adopted.

Real acceptance needs a sandbox merchant/private Ecommerce key and one sandbox
Woo order with exact numeric order ID, display number, and charge ID. Supply
credentials through the operator's private environment. Capture a redacted
charge field list and status, repeat the command, and reconcile the staging GL.
Use a failed or authorized-only fixture and partial/full refund examples to
verify the reviewed exception path. Keep Ecwid and production posting in service
under their existing settings. Disable the staging ERP capture flag to stop
new accounting writes.
