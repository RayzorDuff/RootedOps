# Clover sandbox evidence and WooCommerce gateway review

This is RootedOps #26 development evidence, not merchant approval or checkout
acceptance. No live charge, capture, refund, void, subscription or account change
is implemented or authorized here. Clover remains the immediate processor; Moov
is outside this milestone.

## Reviewed distribution and identity contract

Reviewed the WordPress.org `clover-payments-for-woocommerce` 2.3.2 archive,
SHA256 `c0c58e50c905b5bcbfa55b72c0aa178a6fb5b9eb2cebd9b013f6c7618754e4f5`.
The archive declares WordPress >=6.1/PHP >=7.4 and tested through WordPress 6.9.
Our staging target is WordPress 7.1.4/WooCommerce 11.2.1/PHP 8.3: minimum versions
are satisfied, but compatibility is **not** established by those minimums.
The source still contains direct card-detail post-meta access and an HPOS TODO;
classic checkout, Checkout Blocks and actual HPOS behavior need separate tests.
No vendor copy, source customer records or credentials belong in this repository.

| Identity | Meaning |
| --- | --- |
| `payment_method=clover_payments` | Exact ID in reviewed gateway source; map explicitly to processor Clover |
| Woo `id` | Stable Woo order identity used by ERP/MP |
| Woo `number` | Display order number; retain separately, including prefixes |
| Woo `transaction_id` | Ecommerce **charge** ID in this gateway; not automatically a v3 payment ID |
| Charge `external_reference_id` | Plugin uses Woo display order number on charge creation |
| Refund `external_reference_id` | Plugin uses numeric Woo order ID on refund creation |
| Woo refund ID / Clover refund ID | Separate identities; do not collapse or infer equality |

A transaction ID can be set for authorization and failed-charge responses. A Woo
paid/completed status or nonempty ID does not prove capture. Sandbox evidence
requires an explicit reviewed numeric-ID/display-number crosswalk. The durable
normalized event shape is unchanged: enriching a retry must not alter the original
inbox payload under an existing event identity. The signed raw Woo body remains
archived by the inbox; never invent display numbers from numeric IDs.

## Read-only evidence adapter

`integrations/commerce/clover_sandbox.py` only fetches a single charge using GET
at the fixed Clover sandbox endpoint. It has no payment mutation methods and no
production URL switch. Construction requires explicit enablement, dedicated
`shop-test`/`synthetic` scope, reviewed merchant binding and a private sandbox key.
The merchant/key binding must be independently confirmed in the sandbox account;
a response alone does not establish merchant entitlement or settlement identity.

The adapter refuses redirects, malformed IDs, oversize responses, live/missing
sandbox flags, lists/ambiguous results, missing capture fields, failed or merely
authorized charges, partial captures, currency/amount/refund drift, and mismatched
charge or display-order references. Minor units are exact nonnegative integers;
USD/CAD are the explicitly supported two-minor-unit currencies. No rounding is
used to make totals agree. Transport errors omit credentials and provider bodies;
card/source/customer data is not returned in evidence. Only an authenticated
trusted fetch may mark evidence `verified_adapter`; never configure the transport
from webhook input or relabel an incoming webhook as verified evidence.

Example wiring, with secrets supplied privately (no credential values in source):

```python
import os
from clover_sandbox import CloverSandboxEvidence
client = CloverSandboxEvidence(
    site_key='shop-test', merchant_id=os.environ['CLOVER_SANDBOX_MERCHANT_ID'],
    private_key=os.environ['CLOVER_SANDBOX_PRIVATE_KEY'], enabled=True)
evidence = client.evidence(normalized_order, reviewed_order=reviewed_woo_identity)
```

Existing reconciliation checks run before evidence is returned. Money comparison
now uses exact Decimal values, fixing false mismatches between `0` and `0.00` or
`15` and `15.00`. Invoice/payment creation and physical inventory mutation remain
outside this adapter. Tests use synthetic provider replies only; no credentials
or live API requests were used. Actual response shape is an unresolved sandbox
acceptance gate: missing fields fail closed, including contradictory examples in
provider tutorial pages. Do not relax checks merely to fit an unverified response.

## Installation and remaining acceptance

The plugin defaults to **production** environment. Before any isolated activation,
set local gateway `enabled=no`, `environment=sandbox`, keep keys blank and retain
staging email/HTTP/payment blocks. The actual sandbox setup requires its own
merchant ID plus public/private ecommerce tokens (Hosted iFrame + API/SDK type).
Do not reuse production tokens. Configure restricted sandbox egress only in a
separate reviewed payment test environment; do not enable production outbound
integrations in restored databases to make checkout work.

Still required: plugin runtime/PHP/HPOS/blocks checks; actual sandbox charge lookup
and field/currency/reference verification; authorization/capture, failed and
abandoned payment, retry/redelivery, void, full/partial refunds, tax/shipping and
settlement references; ERP financial identity and MP reservation/physical shipment
reconciliation. Preserve source charge/payment/refund/settlement identifiers and
verify every retry without duplicate posting or fulfillment. The business must
confirm post-Ecwid merchant entitlements, online acceptance, fees/tier, credential
continuity and settlement behavior with its provider. No Ecwid cancellation or
merchant downgrade follows from these tests.

Sources reviewed:

- https://wordpress.org/plugins/clover-payments-for-woocommerce/
- https://docs.clover.com/dev/docs/configuring-the-clover-payment-extension
- https://docs.clover.com/dev/reference/getchargescharge
- https://docs.clover.com/dev/docs/get-a-charge
- https://docs.clover.com/dev/docs/create-a-charge
- https://docs.clover.com/dev/reference/createrefund

Run `make commerce-test` for the mocked evidence/normalization/reconciliation
contracts. Live checkout evidence must remain distinct from these unit tests.
