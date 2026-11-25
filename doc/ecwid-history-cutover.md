# Ecwid history: Woo orders and ERP draft Sales Orders

This operator runner imports existing Ecwid orders without collecting payments,
moving MP/Woo stock, replaying fulfillment, or sending notifications. It does not
submit ERP Sales Orders, create invoices/payments/credit notes, or establish the
current financial receivable. Historical financial posting remains a separate
accounting review, including refunded and delivered-but-awaiting-payment orders.

Use `scripts/commerce_history_cutover.py preview --source PRIVATE/ecwid-source.json
--receipts PRIVATE/history`. Source/receipt files must be private (source 0600,
directory 0700). Preview reads native Woo/ERP customers and products and writes a
private review plus digest. It makes no application writes. No customer lists,
credentials or exported orders belong in Git.

Existing Woo accounts and ERP Customers are reused; unresolved/ambiguous ERP
purchasers stop the preview. A recorded sale with an existing ERP Customer but no
Woo login imports as a named Woo guest, retaining its billing identity and email.
No login or duplicate ERP Customer is created. Anonymous orders use Woo guest / the reviewed ERP
`Dank Mushrooms Web Guest`. Source product identity resolves renamed SKUs before
SKU fallback. Retired/unmapped merchandise retains original name/SKU on Woo lines;
ERP uses explicit nonstock `ECWID-HIST-<source-product-id>` Items when no enabled
leaf Item exists. No sellable product is created or enabled.

Order total, subtotal, shipping, discount and tax must balance exactly before
either destination is touched. Header tax remains authoritative: source line tax
can be absent or differ by cents. Cent allocation distributes the existing order
tax/discount over historical lines, without calculating a new rate. Original line
tax is retained as metadata. Source dates are preserved; no payment timestamp is
invented. All supported source amounts are USD; a differing reported USD total or
tax-inclusive source requires review rather than an inferred conversion.

Install the tracked `rootedops-ecwid-history.php` MU plugin before applying. It
prevents subsequent historical orders from becoming payable, changing stock,
sending emails or generating live order webhooks. The compose bind preserves it
on future container recreation. Installing this plugin does not enable live MP
fulfillment/publication.

Validate all draft documents in the production ERP without retaining them using
`scripts/commerce_history_cutover.py rehearse --source PRIVATE/ecwid-source.json
--receipts PRIVATE/history --review-sha DIGEST`. This exercises native Item,
Customer, Sales Order and exact-total validation, then rolls the transaction back.
Woo is untouched. Inspect the private result and stop on any mismatch/error.

After preview and destination-native acceptance, apply using the exact reported
digest: `scripts/commerce_history_cutover.py apply --source PRIVATE/ecwid-source.json
--receipts PRIVATE/history --review-sha DIGEST`. Take current destination backups,
keep Woo checkout restricted during import, and do not edit source/configuration
between preview and apply. No broad restore of a live store is the retry strategy.

ERP creates all draft Sales Orders in one transaction and checks that invoice,
payment, stock-ledger and email-queue counts did not change. Woo commits each order
with a durable source key/hash. The two systems cannot share one transaction: if
the second destination fails, rerunning the same reviewed plan reuses the first
destination's committed records. Private `erp-result.json` and `woo-result.json`
map every source order to its destination ID. Changed source/mapping/destination
records require reconciliation, not overwriting or dropping identity markers.

`AWAITING_PAYMENT` maps to Woo on-hold even when source fulfillment is delivered;
the separate original fulfillment status is retained. Paid shipped/delivered maps
to completed; paid awaiting-processing maps to processing. Refunded status is
retained without inventing a refund amount or issuing a new refund. The open
source order stays outside live Woo intake and retains its existing Ecwid/MP hold;
operational handover must reuse that commitment rather than reserve twice.

Unpaid/unfulfilled checkout attempts are excluded from this sales-history import;
the preview lists their IDs. They are not declared sales or payment receipts.
Delivered/shipped records are retained even if their source payment is awaiting,
and paid/refunded records are retained independently of fulfillment state.

Tests cover exact money, changed SKUs, retired Items, customer ambiguity, source
drift and duplicate identities. Disposable native Woo acceptance covers import,
retry, discounts/tax totals, unpaid status, payment blocking and unchanged stock.
Production preview and native ERP draft acceptance are still operator steps, not
proof supplied by the pure conversion tests.
