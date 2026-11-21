# Canonical Woo hostname: dankmushrooms.net

Owner procedure, 2026-11-21. This changes the URL of the existing Woo installation on the production Linode. Keep its Compose project `dank-store-test`, database, volumes, Woo IDs, ERP links and MP reservations. `erp.danks.store` stays the ERP destination. Ecwid remains publicly available at its current addresses throughout this preparation. Do not change danks.store DNS/routing yet. After the later storefront cutover, danks.store becomes a deprecated HTTPS redirect to dankmushrooms.net.

Run one block at a time. Send only non-secret results. Do not paste configuration files, database exports, webhook bodies, authorization headers, API keys or private customer details. Stop after block 1 for review of the actual DNS/TLS/routing. The templates assume WP port 8097, customer receiver 8100 and order receiver 8102; these must be confirmed from installed services. A missing receiver is an explicit blocker, not evidence to enable it.

## Identity contract

| Setting or reference | Keep / change |
| --- | --- |
| WP home and siteurl | Change to https://dankmushrooms.net |
| Customer sync woo_site, customer_sites dictionary and delivery route key | Keep shop-test.danks.store |
| Existing Commerce Customer Link source_key / Woo ID | Keep unchanged |
| Order/MP/inbox logical provider + site + order/line IDs | Keep woocommerce + danks.store + existing numeric IDs |
| ERP commerce_customer_sync.woo_origin | Change transport only to https://dankmushrooms.net |
| Worker woo_origin; n8n MP_COMMERCE_WOO_ORIGIN | Change transport only to https://dankmushrooms.net |
| Webhook delivery URLs and secrets | Retain old HTTPS endpoints during transition |
| Ecwid public routing, history and migration mappings | Keep unchanged |

Do not search-replace store keys, private JSON dictionaries, ERP links, webhook options, Woo GUIDs, historical orders or inbox receipts. No record reimport or customer rematching is needed. The new ERP setting is opt-in and validates the exact origin and same-installation approval. Missing woo_origin retains the current behavior.

## 1. Read-only preflight — production Linode

```bash
(
  set -eu
  cd ~/RootedOps
  git log -1 --format='RootedOps %h %s'
  printf 'Modified tracked files: '
  git status --porcelain --untracked-files=no | wc -l
  dc=(sudo docker compose --env-file .env \
    -f docker/docker-compose.dank-wordpress.yml -p dank-store-test)
  for option in home siteurl; do
    "${dc[@]}" run --rm --no-deps -T dank-wordpress-cli option get "$option"
  done
  getent ahostsv4 dankmushrooms.net || true
  sudo nginx -t
  sudo ls -l /etc/nginx/sites-enabled
  sudo ss -ltn '( sport = :8097 or sport = :8100 or sport = :8102 )'
  for host in shop-test.danks.store dankmushrooms.net; do
    curl -sS --max-time 10 -o /dev/null \
      -w '%{http_code} %{url_effective} redirect=%{redirect_url}\n' \
      "https://$host/my-account/" || true
  done
)
```

Success: existing home/siteurl still shop-test; clean checkout; NGINX valid; current WP reachable. Net may still be unconfigured. STOP and return results. Resolve its destination, certificate and any existing vhost before installing another one. Missing 8100/8102 requires reviewing installed receiver units and private routing, without exposing secrets. Never redirect a signed POST to compensate for an absent receiver.

## 2. Merge and back up — Linode, agreed service window

Merge RootedOps #120's prerequisites and this hostname follow-up; MP #116 precedes its hostname follow-up. Keep all existing activation flags. Use the merge order in [fulfillment preparation](commerce-fulfillment-launch.md). Update the clean checkout with `git pull --ff-only`; STOP on local changes or a merge conflict. Follow the ERP image deployment procedure in [the Linode runbook](dank-woocommerce-linode.md), using commerce 0.3.6, for the existing production site. Do not create a new bench. STOP if the installed app version is older after deployment.

Run the existing backup/verification blocks A3–A5 in that runbook before changing configuration. In the same shell prepare a private hostname backup:

```bash
cd ~/RootedOps
umask 077
DOMAIN_BACKUP="$HOME/commerce-migration/hostname-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 -p "$DOMAIN_BACKUP"
dc=(sudo docker compose --env-file .env \
  -f docker/docker-compose.dank-wordpress.yml -p dank-store-test)
wp() { "${dc[@]}" run --rm --no-deps -T dank-wordpress-cli "$@"; }
"${dc[@]}" exec -T dank-wordpress-db sh -ec \
  'exec mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines --triggers "$MARIADB_DATABASE"' \
  > "$DOMAIN_BACKUP/wordpress.sql"
test -s "$DOMAIN_BACKUP/wordpress.sql"
"${dc[@]}" exec -T dank-wordpress tar -C /var/www/html -czf - . \
  > "$DOMAIN_BACKUP/wordpress-files.tgz"
tar -tzf "$DOMAIN_BACKUP/wordpress-files.tgz" >/dev/null
wp option get home > "$DOMAIN_BACKUP/home.txt"
wp option get siteurl > "$DOMAIN_BACKUP/siteurl.txt"
sudo tar -C /etc -czf "$DOMAIN_BACKUP/nginx.tgz" nginx
sudo docker exec erpnext-backend cat \
  /home/frappe/frappe-bench/sites/erp.danks.store/site_config.json \
  > "$DOMAIN_BACKUP/erp-site-config.json"
cp .env "$DOMAIN_BACKUP/rootedops.env"
printf 'Private hostname backup: %s\n' "$DOMAIN_BACKUP"
```

Success: SQL nonempty and tar archives readable; existing off-host backup verification passes. Copy the private hostname backup off-host through the existing backup process. STOP if any check fails. This backup contains secrets/customer data. Never upload it to GitHub. Do not restore the entire Woo DB after any new orders or payments; use the scoped rollback below.

## 3. Prepare net DNS, HTTPS and endpoint routing — owner / Linode

Owner: point **dankmushrooms.net only** to the same Linode. Preserve all current danks.store/Ecwid records. Keep public Woo checkout restricted using its already-reviewed access restriction. Do not expose checkout merely by adding this vhost. If the existing restriction is hostname-specific, extend it to net before publishing DNS. Keep authentication restrictions off machine webhook endpoints; signature verification remains mandatory there.

After block 1 confirms no conflicting net vhost and the documented ports, install the reviewed templates:

```bash
cd ~/RootedOps
sudo install -m 644 nginx/snippets/dank-commerce-webhooks.conf \
  /etc/nginx/snippets/dank-commerce-webhooks.conf
sudo install -m 644 nginx/production/dank-wordpress-canonical.conf \
  /etc/nginx/sites-available/dank-wordpress-canonical
sudo ln -s /etc/nginx/sites-available/dank-wordpress-canonical \
  /etc/nginx/sites-enabled/dank-wordpress-canonical
sudo nginx -t
```

STOP before reload if syntax fails, duplicate server/location exists or ports differ. Review actual existing shop-test HTTPS vhost; retain its current customer webhook location. Add only the missing exact order location from the snippet. If neither exists, include the snippet inside its HTTPS server block. Do not duplicate existing locations or replace its TLS configuration. The precise old-vhost edit depends on block 1 and is a stop point until that evidence is reviewed.

When the resulting configuration is reviewed:

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d dankmushrooms.net
sudo nginx -t
curl -sS --max-time 10 -o /dev/null -w '%{http_code}\n' \
  https://dankmushrooms.net/my-account/
```

Success: valid net-only certificate and the same WP installation. STOP on certificate failure, wrong site or unexpected redirection to Ecwid. Keep the old shop-test HTTPS endpoint serving requests directly. No server-level `return 301/302` may supersede exact webhook locations. The signed paths stay `/webhooks/woocommerce-customer/shop-test.danks.store` and `/webhooks/woocommerce/danks.store`, on both hosts. `proxy_pass` has no URI suffix and preserves the request body and signature header. No new receiver activation is authorized by this hostname step.

## 4. Host-dependent external connections — owner in account consoles

Before changing WP options, add `https://dankmushrooms.net/*` to the existing Google Maps browser key's website restrictions; retain shop-test temporarily and the existing API restrictions. Also allow the bare net origin if the console requires it. Do not expose the key. After the move, test the drawn delivery zone/map and browser console. [Google's restriction guidance](https://developers.google.com/maps/api-security-best-practices).

Installed evidence: WooCommerce Shipping 2.5.1 supplies label capability; Flexible Shipping USPS 3.6.3 is also active. Do not install another label plugin for this hostname change. Review WooCommerce → Settings → Shipping → WooCommerce Shipping connection/status, origin address and existing payment/account connection before and after. Confirm existing labels remain visible; follow supported connection recovery before disconnecting or recreating the site/account. Postage purchasing is a separate explicit paid operator action. [Woo Shipping connection and label documentation](https://woocommerce.com/document/woocommerce-shipping/).

Review the installed Clover Payments 2.3.2 website gateway's registered site/callback/allowed-domain fields with the owner and update only hostname-dependent settings, preserving merchant ID, environment and credentials. Do not infer capture from Woo status. Keep public checkout restricted and defer any real charge to the explicit owner order. Clover Flex/REST Pay Display does not gate this work.

Recheck FluentSMTP test mail to the owner's designated test destination; preserve sender/authentication settings unless its provider rejects the new URL. Review any Google/Meta plugin connection/site URL, but defer feed/ownership changes to the cutover checklist. STOP if a required map, payment, shipping or email connection fails.

## 5. Change canonical WP URLs — Linode, no public checkout

Run only after backups, deployed plugin/commerce 0.3.6, dual-host routes and valid net HTTPS are confirmed. The Compose project and volumes stay unchanged. Use the existing `wp` shell function from block 2:

```bash
wp option update home https://dankmushrooms.net
wp option update siteurl https://dankmushrooms.net
wp option get home
wp option get siteurl
wp cache flush
```

Success: both options net. Log in afresh at net; WordPress cookies are hostname-specific. STOP on redirect loop or authentication failure. Verify My Account, product media, checkout restriction and both webhook endpoints before content changes.

Preview only scoped post content/excerpts:

```bash
"${dc[@]}" run --rm --no-deps -T \
  -v "$PWD/scripts/commerce_wordpress_hostname.php:/tmp/commerce_wordpress_hostname.php:ro" \
  dank-wordpress-cli eval-file /tmp/commerce_wordpress_hostname.php preview
```

Success: `preview changed_content_rows=N`. It excludes options, metadata, GUIDs, orders and all private integration records. It rewrites only exact HTTPS old-host URLs in allowed storefront post types, preserving serialized array keys and recalculating serialized lengths. Serialized objects stop for manual review. Review count before apply; do not run a broad database search-replace. Theme/menu/widget/custom-field URLs outside this scope require individual UI edits, with their own backups.

Apply after preview review. CLI runs as UID 33, so give only its private journal directory that ownership:

```bash
sudo install -d -m 700 -o 33 -g 33 "$DOMAIN_BACKUP/content-private"
"${dc[@]}" run --rm --no-deps -T \
  -v "$PWD/scripts/commerce_wordpress_hostname.php:/tmp/commerce_wordpress_hostname.php:ro" \
  -v "$DOMAIN_BACKUP/content-private:/hostname-private" \
  dank-wordpress-cli eval-file /tmp/commerce_wordpress_hostname.php \
  apply /hostname-private/content.json
```

Success: expected changed count and private mode-0600 journal. STOP on error. Never overwrite the journal. Back it up privately. It stores only the exact changed fields' before/after values.

## 6. Transport-only private configuration — Linode

Preserve all incoming webhook delivery URLs, logical route keys, credentials, cutoff, approved orders and flags. ERP helper backs up site_config once, then changes only `same_woo_installation` and customer `woo_origin`:

```bash
sudo docker exec -i --user frappe erpnext-backend python3 - storefront-domain \
  < scripts/commerce_live_approve.py
sudo docker exec --user frappe erpnext-backend \
  bench --site erp.danks.store clear-cache
```

Success: `ERP storefront-domain applied`. STOP on a configuration mismatch; do not create a new customer config. This keeps `woo_site: shop-test.danks.store`. Scheduled ERP projection uses the same logical site and new transport URL.

For the existing private order-worker configuration, use the verified `LIVE_ORDER_CONFIG` path from the earlier operator setup. If that path or its supervising unit is unknown, STOP and inspect it privately; do not invent/create a replacement config. No order worker deployed yet means this step awaits that deployment, with its desired transport recorded as net.

```bash
test -n "${LIVE_ORDER_CONFIG:-}"
python3 scripts/commerce_storefront_config.py "$LIVE_ORDER_CONFIG"
```

Success: transport updated; store identities/flags retained; a mode-0600 `.before-dankmushrooms-net` backup exists. The helper refuses an unknown old origin or non-private file. Set `MP_COMMERCE_WOO_ORIGIN=https://dankmushrooms.net` in private `.env` using the existing private-configuration procedure. Do not change `MP_COMMERCE_FULFILLMENT_ENABLED`, Woo stock or payment enable flags. Import the MP hostname workflow follow-up using the normal versioned workflow deployment. It preserves webhook names and validates the new origin.

Restart only affected worker units identified by the installed service preflight. Recreate n8n only in an agreed shared-service window and only when this env setting is used by its installed workflow. Use the existing Compose project and its normal core compose files, adding `-f docker/docker-compose.commerce-hostname.yml`, then `up -d --no-deps n8n`; never `down` or `--remove-orphans` on this shared server. STOP if any target/reference/readback fails. Native ERP configuration may be cached in long-lived workers: use the existing ERP service reload procedure in the shared-service window if cache clearing alone does not refresh it. Do not restart unrelated applications.

## 7. Acceptance — owner browser plus installed workers

Retain old delivery URLs initially. In Woo webhook settings record topic/status and sanitized delivery destination only; do not expose secret. Both customer and order receivers must validate the raw body signature before parsing and persist before HTTP 202. Test a synthetic invalid-signature POST to each old/new configured endpoint only after the receiver is available:

```bash
for host in shop-test.danks.store dankmushrooms.net; do
  for path in woocommerce-customer/shop-test.danks.store woocommerce/danks.store; do
    curl -sS --max-time 10 -o /dev/null \
      -w '%{http_code} redirect=%{redirect_url}\n' \
      -H 'Content-Type: application/json' -H 'X-WC-Webhook-Signature: invalid' \
      --data-binary '{}' "https://$host/webhooks/$path"
  done
done
```

Expected HTTP 400 from the current receiver, no Location/redirect, no durable business effect. STOP on 2xx, any 3xx, 401 access-wall interception or 5xx. Preserve existing access rules while making the exact webhook routes reachable and signature protected.

Use one existing owner-controlled linked Woo customer, recording only numeric Woo ID and redacted ERP reference:

1. In net My Account save a harmless account-name edit; verify signed customer delivery gets 202 and updates the same ERP Contact/Customer/link. Secondary email survives. Save billing/shipping separately if touched by deployment. No new Customer or link may appear.
2. Edit one reviewed ERP Contact field; run the existing projection timer or approved command. Woo net profile changes on the same numeric ID. Project again: `unchanged`. Check requests go directly to net, without an HTTP redirect. Restore the test field through the same route.
3. With public checkout restricted, create/update the approved owner fixture order on net; do not charge or buy postage unless explicitly chosen by the owner. Verify Woo's native signed delivery to the retained old endpoint returns 202 and the existing inbox/MP/ERP order references remain stable. Replay that same Woo delivery and verify one reservation/Sales Order. Follow the full hosted lifecycle acceptance in the fulfillment guide once its prerequisites are deployed; an unpaid hostname test does not prove accounting or fulfillment.
4. In MP, Open Woo order must retrieve Woo's current generated admin URL for the same numeric order and open net with normal WP permissions. An old browser tab may retain an old URL; resolve a fresh link. Partial shipments remain open; only committed MP dispatch completes fulfillment. Preparing a label does not commit MP stock.

Record dated installed results, sanitized delivery/receipt IDs and document references in #20/#1 and the fulfillment issues. STOP if either sync direction fails or any duplicate/link drift appears. The live hostname acceptance remains pending until operator evidence is returned.

## 8. Rollback and later Ecwid cutover

If hostname acceptance fails, restrict checkout first and leave both HTTPS vhosts/endpoint routes alive. Pause only affected new transport callers through their installed service controls while retaining queued receipts. Restore the saved home/siteurl values:

```bash
wp option update home "$(cat "$DOMAIN_BACKUP/home.txt")"
wp option update siteurl "$(cat "$DOMAIN_BACKUP/siteurl.txt")"
wp cache flush
```

To undo only content changed by this migration:

```bash
"${dc[@]}" run --rm --no-deps -T \
  -v "$PWD/scripts/commerce_wordpress_hostname.php:/tmp/commerce_wordpress_hostname.php:ro" \
  -v "$DOMAIN_BACKUP/content-private:/hostname-private" \
  dank-wordpress-cli eval-file /tmp/commerce_wordpress_hostname.php \
  restore /hostname-private/content.json
```

Success: exact original changed rows restored. The journal restore compares current values to its recorded after-values and aborts the transaction if content changed meanwhile; resolve those rows manually rather than overwrite newer content. Keep net resolving to the same WP during recovery. Restore **only transport settings** to shop-test from the private backups; preserve newer receipts, approvals and records. Never restore the entire site_config or worker JSON over newer operational changes without reviewing the difference. Keep the same logical store identities. Revalidate customer requests and repeat a safe signed replay after resuming the existing services.

At the later owner-approved public cutover, pause Ecwid checkout, reconcile outstanding commitments/opening inventory, and switch danks.store HTTPS frontend traffic to net using temporary 302s. Preserve any established exact signed webhook routes ahead of frontend redirects. Review saved sitemap paths/QR labels at net with no hop through shop-test, verify maps/shipped/pickup/delivery/tax/email/Clover, then owner purchase and lifecycle trace. Only after verification change frontend redirects to 301. Retain Ecwid for rollback and preserve Woo orders/payments already accepted. Keep the feed ownership/item-ID transition, first-payout reconciliation and Clover entitlement after Ecwid cancellation on the retirement checklist. Settlement/fee evidence stays visible; Flex is independent.

## Evidence status

- Installed operator evidence: original home/siteurl shop-test; active Woo/Clover/Shipping/USPS/Maps-zone/FluentSMTP versions recorded above. Customer sync previously demonstrated both ways.
- Repository implementation: explicit net transport origins, stable aliases, guarded config tools, content journal and dual-host route templates.
- Local test result and CI links are recorded in the hostname PR; disposable fixtures prove serialization/exclusions/restore and identity behavior.
- Awaiting owner: current net DNS/TLS/NGINX and receiver ports; merge/deployment; Maps/Clover/Shipping account connections; existing-customer updates both ways; signed native order delivery on the changed host. No hosted setting, payment, postage or Ecwid routing changed by repository tests.
