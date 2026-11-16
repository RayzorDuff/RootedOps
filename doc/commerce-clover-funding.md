# Clover funding and processing fee draft reconciliation

Clover documents GET charge details as transaction evidence. The public charge
examples do not establish actual processor fees or deposit composition. Clover's
Finances section describes closeout/deposit summaries. The actual fee schedule,
batch detail and access available to Dank Mushrooms still need merchant evidence.
Merchant identifiers on a charge may depend on the transport and the account.
Application marketplace billing reports and customer service charges do not
represent the card-processing fees withheld from the merchant.

- [Ecommerce charge reference](https://docs.clover.com/dev/reference/getchargescharge)
- [Example charge response](https://docs.clover.com/dev/docs/get-a-charge)
- [Clover Finances and deposits](https://docs.clover.com/dev/docs/test-merchants-get-the-new-clover-dashboard)
- [Monthly statement access](https://clover.streamlinepayments.com/hc/en-us/articles/4493016775188-How-can-a-merchant-access-their-monthly-statement)

Use the most detailed available processor funding report or statement; an API
source must have the same merchant, settlement and bank trace evidence. No
merchant-specific funding API or actual export layout was established here.
The manual normalization path does not infer fees from gross less net.

1. Match one funding/deposit reference and bank row (trace/entry ID, date, and
   amount) to the reviewed merchant and currency. If the processor debits fees
   separately, match the separate fee debit and reference.
2. Retain the bank and processor originals privately, and use `sha256sum` on
   the reviewed funding source. Record each actual capture, fee, reversal, or
   classified adjustment. List POS/other Clover sales along with Woo sales
   when the deposit combines channels. Use ERP voucher references for the
   gross already booked per channel. The same ERP voucher may group lines within
   one batch if its GL matches their combined clearing amount. Split vouchers
   spanning batches require review.
3. The draft for a deposit debits Bank for net, debits merchant fee expense
   for actual withheld fees, clears the already-booked gross by channel, and
   records separately classified adjustments. A separately billed fee draft
   debits fee expense and credits Bank against its matched debit. Previously
   posted refund/chargeback clearing amounts reduce the clearing balance of a
   deposit. An unclassified adjustment or unbalanced batch stops.
4. ERP verifies company/currency and posted clearing GL before drafting the
   Journal Entry. Reimports return the same draft by merchant and funding
   reference. Reuse of an underlying bank, funding line or clearing voucher
   across batches stops for review. This path uses a dedicated ERP site and
   leaves the Journal Entry in draft.

Use a private JSON manifest with keys `merchant`, `environment` (`sandbox` or
`live` as source classification), `reference`, `currency`, `source`
(`funding_report`, `merchant_statement` or `verified_funding_api`),
`source_sha256`, `kind` (`deposit` or `separate_fee_debit`), `net`, and
`bank` containing `reference`, `date`, `amount` and matching `kind`.
Normalize the private detail to the following columns. When channel clearing
was already posted, give a `DocType:ID` voucher reference.

```csv
kind,reference,channel,amount,erp_reference
capture,synthetic-woo-ref,woo,60.00,Payment Entry:SYN-WOO
capture,synthetic-pos-ref,pos,40.00,Journal Entry:SYN-POS
processing_fee,synthetic-fee-ref,,3.00,
reserve_withheld,synthetic-reserve-ref,,2.00,
```

Configure the reviewed policy with `merchant`, `environment`, `company`,
`currency`, `bank`, `fees`, `clearing_by_channel` and named `adjustments` with
`account` and `side`. Copy the policy into the private staging site setting
`commerce_clover_settlement_pilot` and add `enabled: true` only during the
staging test. Use a staging Accounts Manager credential in a private curl config.

```bash
python integrations/commerce/import_clover_funding.py \
  "$FUNDING_MANIFEST" "$FUNDING_DETAIL_CSV" "$FUNDING_POLICY" "$PRIVATE_ERP_PAYLOAD"
curl --silent --show-error --fail-with-body --config "$ERP_CURL_CONFIG" \
  --header 'Content-Type: application/json' --data-binary "@$PRIVATE_ERP_PAYLOAD" \
  https://erp-test.danks.store/api/method/rootedops_commerce.clover_settlement.draft_settlement
```

Expect `message.status: draft` and the same Journal Entry reference on exact
retry. Disable the staging flag after the test. Keep the draft for review.

## Evidence needed from the merchant

Provide a redacted **Clover funding/Deposits detail export or processor funding
report for one complete payout**, the **monthly statement page that itemizes
processing fees**, and the **matching bank credit**. Keep stable pseudonyms
consistent across files for merchant, charge, batch, settlement and bank trace.
Retain the funding date, gross, net, currency, each posted fee/refund/chargeback/
reserve/adjustment, and any Woo/POS indicator or transaction reference that ties
to each sale. Include the matching bank debit if fees are billed separately.
Redact account numbers, card data, customer data and credentials. If the merchant
portal provides no batch-level fee detail, include the statement's exact fee
period and any report that associates the statement with funding batches. An
unresolved difference remains for review.
