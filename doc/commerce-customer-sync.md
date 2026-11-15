# WooCommerce and ERPNext customer sync

## Profile ownership

| Data | Rule |
| --- | --- |
| ERP Customer | Retains the accounting identity, group, territory and existing links. New registrations create an Individual in staging using the configured defaults. |
| Account | The linked ERP Contact owns the name and primary email. An explicit Woo My Account save can update them if ERP has not also changed. |
| Billing | The linked ERP Billing Address owns the street, city, state code, postal code and country. The linked Contact owns the primary billing phone. |
| Shipping | The linked ERP Shipping Address owns the same postal fields. |
| Orders | Authenticated Woo order snapshots carry a numeric registered customer ID or a guest marker. Registered orders resolve the crosswalk, and guests use the reviewed draft's Customer. Woo checkout addresses stay in the order snapshot. |
| Other fields | Marketing preferences, passwords, payment fields, alternate recipients and billing email remain outside the profile exchange. |

The crosswalk is keyed by Woo store and customer ID. It links Customer, Contact and distinct Billing and Shipping Address records, with an optional Ecwid Commerce Migration Identity. Review email matches before linking. Use account-only Address records and keep historical order addresses with their order snapshots.

Woo emits a signed action after registration and explicit account or address saves. It carries a unique receipt ID and a hash of the saved fields. The inbox verifies the raw signature and persists the receipt before acknowledgement. The worker fetches the account by ID. An older action whose fields no longer match Woo returns `stale`. The inbox resumes at the ERP receipt after a retry. ERP customer creation, documents and the crosswalk use one database transaction. Checkout data alone cannot apply a profile edit.

A last-synchronized hash per profile section detects conflicting changes. If ERP and Woo both diverge, review the crosswalk status and align the selected fields on both sides before retrying projection. ERP-to-Woo projection uses a live comparison immediately before the Woo REST update. Woo's standard REST update has no conditional write, so an edit arriving between the GET and PUT is an unresolved concurrency window to exercise before production. A failed or lost Woo response can be retried and acknowledged by reading the projected values. The REST projection does not fire the outbound Woo form hooks.

## Isolated activation

1. Verify the matched `erp-test2.danks.store` and `shop-test2.danks.store` pair (or both `test` hosts) and a mail sink. Use fictitious addresses. Confirm ERPNext can render an Address using its standard country or default Address Template. Deploy the ERP app and run `bench --site erp-test2.danks.store migrate` in that bench. Drain pre-upgrade order deliveries before enabling the registered-order requirement. Restart the staging inbox process with this branch's code.
2. Set `commerce_customer_sync` in the **staging** ERP site's private config. Use a Woo REST read/write credential for the matching shop and a role-authorized ERP API credential for the inbox worker. Set `project_enabled` to false at first.

   ```json
   {
     "enabled": true,
     "project_enabled": false,
     "woo_site": "shop-test2.danks.store",
     "woo_authorization": "Basic <private Woo REST credential>",
     "customer_group": "<existing ERP Customer Group>",
     "territory": "<existing ERP Territory>"
   }
   ```

3. Add this block to the **staging** inbox configuration. Retain any existing order sites and use a unique webhook secret, at least 32 characters, per customer site.

   ```json
   {
     "customer_sites": {
       "shop-test2.danks.store": {
         "erp_base_url": "https://erp-test2.danks.store",
         "secret_envs": ["WOO_CUSTOMER_WEBHOOK_SECRET"]
       }
     }
   }
   ```

   Use the existing loopback test inbox service with `COMMERCE_STAGING_ONLY=1`, the staging `COMMERCE_INBOX_DSN` and the secret above. Initialize the disposable inbox once with `python integrations/commerce/runtime.py init`. Start it with `python integrations/commerce/runtime.py serve --config "$INBOX_CONFIG"`. Publish only the staging ingress location `/webhooks/woocommerce-customer/shop-test2.danks.store` through the existing HTTPS proxy, preserving the body and Woo signature header. The customer worker uses `ERP_AUTHORIZATION` in its environment.

   ```bash
   python integrations/commerce/runtime.py work-customers-once \
     --config "$INBOX_CONFIG" --customer-site shop-test2.danks.store
   ```

   Run that worker regularly while testing. It shares the durable inbox tables and claims customer deliveries only. `status` shows redacted counts. To retry a dead letter, use `replay --event-key woocommerce-customer shop-test2.danks.store RECEIPT_HASH` after fixing the cause.
4. Set `DANK_WP_CUSTOMER_WEBHOOK_ENABLED=1` in the private staging WordPress Compose env and recreate the staging Web service. For a different test deployment layout, mount only `wordpress/dank-mu-plugins/rootedops-customer-webhook.php` in the staging web root's `wp-content/mu-plugins` and set the same `ROOTEDOPS_CUSTOMER_WEBHOOK_ENABLED` constant privately. Add an active WooCommerce webhook with topic **Action**, event `rootedops_customer_profile_saved`, the staging HTTPS ingress URL and the same secret. If the Woo UI sends an unsigned setup ping, the inbox refuses it. Create the webhook directly with a staging WP-CLI `WC_Webhook` save if needed and use a signed account save as the connectivity check.
5. Register one synthetic account in My Account. Confirm one `Commerce Customer Link` and one ERP Contact. Edit My Account details, Billing and Shipping separately. Confirm each relevant ERP section is synced and replay the same request to get a duplicate receipt. Edit the ERP Contact, and call the following authenticated Frappe endpoint twice. It should update Woo once and then return `unchanged`. Enable `project_enabled` only after this check. The ERP scheduler then queues projection every five minutes.

   - `POST /api/method/rootedops_commerce.customer_sync.project_profile`
   - JSON fields `site`, `customer_id`, and `scope` (`account`, `billing`, or `shipping`).
   - Repeat with an intervening different Woo edit and confirm a review status. Exercise stale and invalidly signed deliveries, a duplicate ERP email, a registered order using the same ERP Customer and a guest order preserving the reviewed guest mapping. Confirm neither order overwrites the account address.

Disable by pausing the Woo webhook, disabling the MU-plugin flag, stopping the customer worker and setting `enabled` and `project_enabled` to false in the ERP site configuration. The crosswalk and inbox provide the review history.

## Private Ecwid customer preview

```bash
python integrations/commerce/customer_review.py \
  --customers "$ECWID_CUSTOMERS_CSV" --orders "$ECWID_ORDERS_CSV" \
  --store-id "$ECWID_STORE_ID" --output "$PRIVATE_REVIEW_CSV"
```

Add `--recover-ecwid-ids` with a read-only `ECWID_TOKEN` to populate Ecwid ID candidates. Verify existing ERP and Woo email matches and fill the reviewed ID columns. Use order contact snapshots as evidence of a possible shipping address and phone. An order with a blank email supplies no customer candidate. Marketing consent stays in its own export column.

To preview new ERP customer inserts, mark the reviewed rows `create_erp`, fill `ecwid_customer_id` and the reviewed name, and leave ERP ID columns blank. An optional `approved_contact_order` must identify one shipping contact snapshot. Then compile.

```bash
python integrations/commerce/customer_review.py --compile-reviewed "$PRIVATE_REVIEW_CSV" \
  --store-id "$ECWID_STORE_ID" --customer-group "$ERP_CUSTOMER_GROUP" \
  --territory "$ERP_TERRITORY" --output "$PRIVATE_CUSTOMER_PLAN"
```

A reviewed plan uses the existing `rootedops_commerce.history.import_history` POST with `payload` set to the plan object or its JSON string and requires `commerce_history_import_enabled`. Pilot one approved row and repeat the same payload to verify the existing identity is reused. New identities whose email is already present stop for review. Use the canonical ERP names for existing records rather than importing a second Customer.

Optional Woo provisioning can use the existing staged `integrations/commerce/customers.py:upsert_customer` adapter after mail-sink verification. When the ERP and Woo profiles agree and the links have been reviewed, call `POST /api/method/rootedops_commerce.customer_sync.link_existing`. Pass the mapping as `payload` with `site_key`, `id`, `customer`, `contact`, optional `billing_address`, `shipping_address` and `ecwid_identity`. Keep review CSVs, tokens, exports and customer-bearing evidence in private storage. Record accepted staging results using synthetic IDs and redacted counts.
