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

### Batch 1: Read-only host preflight

Run this on the existing **test2 Linode** from a staging operator shell with Docker access. It reads the deployed configuration and makes local HTTPS probes. The WP-CLI command uses a one-off container with the existing isolation override. No running service is restarted. If test2 is unavailable, coordinate with the storefront rebuild owner before substituting the matched `test` pair and its own deployment files.

```bash
(
set -eu
cd ~/RootedOps
cfg="$PWD/.test-deployment"
test "$(cat "$cfg/TEST_ENVIRONMENT")" = rootedops-full-test
sudo -v

sudo docker compose --env-file "$cfg/.env" -f "$cfg/core.yml" \
  -f "$cfg/private/erp-restored-image.yml" -p rootedops-full-test ps
sudo docker exec rootedops-full-test-erpnext-backend-1 \
  bench --site erp-test2.danks.store list-apps
sudo docker compose --env-file "$cfg/.env" -f "$cfg/dank.yml" \
  -f "$cfg/private/wordpress-offline.yml" run --rm --no-deps -T dank-wordpress-cli eval '
$http_blocked = defined("WP_HTTP_BLOCK_EXTERNAL") && WP_HTTP_BLOCK_EXTERNAL;
echo wp_json_encode([
    "shop" => home_url(),
    "woo" => defined("WC_VERSION") ? WC_VERSION : null,
    "my_account_url" => function_exists("wc_get_page_permalink") ? wc_get_page_permalink("myaccount") : null,
    "account_registration" => get_option("woocommerce_enable_myaccount_registration"),
    "mail_sink_filter" => has_filter("pre_wp_mail", "__return_true") !== false,
    "wp_http_block_external" => $http_blocked,
    "wp_cron_disabled" => defined("DISABLE_WP_CRON") && DISABLE_WP_CRON,
    "customer_webhook_flag" => defined("ROOTEDOPS_CUSTOMER_WEBHOOK_ENABLED") && ROOTEDOPS_CUSTOMER_WEBHOOK_ENABLED
], JSON_PRETTY_PRINT), PHP_EOL;'

for url in \
  'https://shop-test2.danks.store/my-account/' \
  'https://shop-test2.danks.store/wp-json/wc/v3/customers?per_page=1' \
  'https://erp-test2.danks.store/api/method/ping'; do
  host=${url#https://}
  host=${host%%/*}
  curl --noproxy '*' --resolve "$host:443:127.0.0.1" \
    --connect-timeout 5 --max-time 10 --silent --show-error --output /dev/null \
    --write-out '%{http_code} %{url_effective}\n' "$url" || true
done
sudo ss -ltnp 'sport = :8100'
)
```

Expected output and follow-up:

| Probe | Expected or action |
| --- | --- |
| ERP apps and shop identity | `rootedops_commerce` appears for `erp-test2.danks.store`. The Woo version is populated and the shop and My Account URL use `shop-test2.danks.store`. Stop on any mismatch. |
| WordPress controls | The recorded test2 image has `mail_sink_filter: true`, `wp_http_block_external: true`, `wp_cron_disabled: true` and expects `customer_webhook_flag: false` at preflight. If the mail filter is absent, verify an equivalent staging-only sink before registering. A disabled registration option or missing My Account page needs a coordinated staging change. |
| Woo routes | My Account should return 200 for browser acceptance. An unauthenticated Woo REST 401 is expected under the guarded ingress. A 404 or redirect requires checking the My Account URL/guarded browser ingress before proceeding. |
| ERP probe | 200 if the private staging ERP ping is routed. The documented closed ingress typically returns 403. The inbox worker still needs a route to the role-authorized ERP POST methods before activation. |
| Port 8100 | A current inbox should listen on `127.0.0.1:8100`. An empty result means the staging listener must be provisioned. Identify the owner of any existing listener before reusing it. |

The earlier test2 stack puts Woo and ERP on internal networks. Confirm routes from **Woo to the HTTPS ingress**, **the inbox worker to ERP**, and **the ERP backend to authenticated Woo REST** from the actual runtime locations. The host probes above establish host ingress only. The standard staging NGINX renderer proxies Woo REST and optional browser paths. It does not install the customer receiver or route ERP methods. Use exact staging locations for the inbox and private role-authorized ERP API access. Keep the ERP root and other restricted routes closed.

If the offline WordPress guard is still in use, `wordpress-isolation/rootedops-staging.php` returns `staging_egress_blocked` for every HTTP request. Allow only the exact configured HTTPS customer receiver URL in that guard, and allow only its staging host in the WordPress HTTP allowlist if the external HTTP block applies. Verify that the shop container can reach the ingress with trusted TLS. Keep the mail sink, payment isolation and other HTTP restrictions in place. With automatic WP cron disabled, use the staging Action Scheduler/CLI to run `woocommerce_deliver_webhook_async` after each browser save. Check the installed CLI options with `wp help action-scheduler run` and use `wp action-scheduler run --hooks=woocommerce_deliver_webhook_async` from the staging WordPress CLI. This processes the queued delivery rather than synthesizing the hook.

### Batch 2: Activate the isolated services

Proceed after reviewing the preflight and coordinating any changes or restarts. Deploy the tested PR branch in the staging ERP bench, WordPress and inbox only. Keep the private configuration and secrets on the staging hosts.

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
### Batch 3: Run live acceptance

Use a new fixture email under `example.invalid`. Confirm that WordPress and ERP email are captured or suppressed by staging sinks. Use a different fictitious name or address value for each change and wait for its receipt before moving to the next check, except when deliberately testing stale delivery or a conflict.

1. In Woo **My Account → Register**, register the fixture account. If registration uses a setup link, retrieve it in the sink or set the fixture password through staging administration. Run the delivery queue when required, then run the customer worker command from Batch 2. Expect HTTP 202 with `duplicate: false` at the inbox and a completed receipt with ERP status `synced`. Find the linked ERP records by Woo store and numeric customer ID. Record one Customer, one Contact and one Commerce Customer Link. Capture the exact signed body and signature privately from this synthetic delivery, then use the replay commands below. Expect HTTP 202 with `duplicate: true` and the same receipt ID and ERP records.
2. In the linked ERP Contact, add a second fictitious email and keep the first marked primary. In Woo **My Account → Account details**, change the first or last name and the primary email to unused fixture values. Save. Expect the linked Contact details and primary email to change and the secondary email to survive. Then open **My Account → Addresses → Billing address → Edit**, save one address and phone, and verify the linked Billing Address and Contact phone. Open **Shipping address → Edit**, save a different address, and verify the linked Shipping Address. The other address must keep its prior values after each save.
3. With both sides in sync and `project_enabled` still false, change the ERP Contact's first name. Call the projection command twice. Expect Frappe `message.status` to be `synced` and then `unchanged`. Refresh My Account and confirm the new name. For the ordinary conflict, make different edits in the same section on each side before delivering the Woo signal or calling projection. Expect `review_both_changed` with both edits preserved. Reconcile the fixture before the next case. For the timing case, use a staging-only controlled hold on the projection REST PUT after its GET has completed. Save a different value in My Account in that gap, release the PUT, and process the Woo save signal. Record the final Woo value and both statuses. Treat the timing case as pending if the actual staging REST transport cannot be controlled.
4. For a stale signal, hold the worker, save the same Woo section twice with different values, then run the queue and worker. Expect the older receipt to complete with ERP status `stale`, the latest to sync and ERP to retain the latest values. For an invalid signature, submit the captured body with an invalid signature below. Expect HTTP 400 and no new receipt. A duplicate ERP email should produce `review_erp_email_match` and create no second linked Customer.
5. Use two synthetic Woo orders and the existing staging reviewed-draft mappings. Use the linked Woo account for one order and place the other as a signed-out guest. Send the actual staged orders through the existing authenticated order route and worker. Set the registered draft's Customer to the linked ERP Customer or leave it for crosswalk resolution, and set the guest draft's Customer to the explicitly reviewed guest mapping. Expect those Customers on the resulting draft Sales Orders. Give each order a distinguishable order address and compare both linked ERP Address records before and after. Also read the Woo account profile after checkout and record any native checkout write separately from ERP Address changes. Use no live gateway or charge.

Replay the original signed **synthetic** body and probe invalid signatures from a host with staging ingress access. Set the two capture files privately. The header file contains the original `X-WC-Webhook-Signature: ...` header on one line.

```bash
endpoint=https://shop-test2.danks.store/webhooks/woocommerce-customer/shop-test2.danks.store
curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  --header 'Content-Type: application/json' --header "@${SIGNED_HEADER_FILE:?}" \
  --data-binary "@${RAW_WOO_BODY_FILE:?}" "$endpoint"
curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  --header 'Content-Type: application/json' --header 'X-WC-Webhook-Signature: invalid' \
  --data-binary "@${RAW_WOO_BODY_FILE:?}" "$endpoint"
```

To project, prepare a mode-0600 curl config with a single `header = "Authorization: <private staging ERP credential>"` entry. Run this from a shell allowed to reach the private staging ERP route. Use the fixture's numeric Woo customer ID.

```bash
project_account() {
  curl --silent --show-error --fail-with-body --config "${ERP_CURL_CONFIG:?}" \
    --header 'Content-Type: application/json' \
    --data "$(printf '{"site":"shop-test2.danks.store","customer_id":"%s","scope":"account"}' "${WOO_CUSTOMER_ID:?}")" \
    https://erp-test2.danks.store/api/method/rootedops_commerce.customer_sync.project_profile
  printf '\n'
}
project_account
project_account
```

For each test, record the HTTP status, redacted receipt and worker outcome, synthetic record counts and linkage, and final profile state. Keep periodic projection disabled until the live projection and conflict results have been reviewed. With `project_enabled` running, the scheduler queues projection every five minutes.

Disable by pausing the Woo webhook, disabling the MU-plugin flag, stopping the customer worker and setting `enabled` and `project_enabled` to false in the ERP site configuration. The crosswalk and inbox provide the review history.

### Verification checkpoint, 2026-11-15

| Check | Result |
| --- | --- |
| Hosted test and test2 access | All four HTTPS requests timed out from the work session. Direct lookup failed in that session, and it had no direct route or SSH agent for the documented test2 host. Staging deployment, isolation and activation are awaiting the operator preflight. |
| Local and CI checks | `make commerce-test` ran 214 tests with one skip. Commerce foundation, Commerce integration contracts and Fresh host recovery passed on the implementation head. |
| Projection timing window | A local probe ran `project_profile` and `consume_signal` with a controlled Woo transport. A Woo edit inserted after GET and before PUT was overwritten. Projection returned `synced`, repeat returned `unchanged`, and the intervening save signal returned `stale`. Live timing evidence is pending. |
| Live Woo, inbox and ERP | Registration, replay, account/billing/shipping changes, projection, conflict, stale/invalid deliveries and order linkage are pending. PR #101 remains draft. |

## Private Ecwid customer preview

The production import for the November 15 batch is complete. Preserve the accepted mappings: 11 source rows linked to 10 new ERP Customers, rows 6 and 7 share one Customer and Contact with row 6 primary and row 7 secondary, row 9 keeps the existing ERP record, and rows 14–26 were skipped without a matching order email. Skip Ecwid ID recovery and another pilot for this batch. For ongoing account linking use the Woo store and customer ID. The Ecwid migration identity is optional.

The commands below apply to future batches.

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
