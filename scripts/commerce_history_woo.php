<?php
// Executed only by commerce_history_cutover.py through Docker PHP stdin.
require 'wp-load.php';
if (untrailingslashit(home_url()) !== 'https://dankmushrooms.net') throw new RuntimeException('Unexpected Woo origin');
if ($input['action'] === 'snapshot') {
    $users = array();
    foreach (get_users() as $user) $users[] = array('id' => (int)$user->ID, 'email' => $user->user_email);
    $products = array();
    foreach (wc_get_products(array('limit' => -1, 'status' => array('publish','draft','pending','private'))) as $product) {
        $products[] = array('id' => $product->get_id(), 'sku' => $product->get_sku(),
                            'source' => $product->get_meta('_rootedops_source_key', true));
    }
    echo wp_json_encode(array('users' => $users, 'products' => $products));
    return;
}
if ($input['action'] !== 'apply' || !function_exists('rootedops_ecwid_historical_order')) {
    throw new RuntimeException('Install history guards before applying');
}
wp_set_current_user(1);
if (!current_user_can('manage_woocommerce')) throw new RuntimeException('Expected Woo administrator');

// These filters are also active before the new order's metadata has been saved.
add_filter('woocommerce_webhook_should_deliver', '__return_false', PHP_INT_MAX);
add_filter('woocommerce_can_reduce_order_stock', '__return_false', PHP_INT_MAX);
add_filter('woocommerce_can_restore_order_stock', '__return_false', PHP_INT_MAX);
add_filter('woocommerce_can_restock_refunded_items', '__return_false', PHP_INT_MAX);
add_filter('woocommerce_defer_transactional_emails', '__return_false', PHP_INT_MAX);
add_filter('pre_wp_mail', '__return_true', PHP_INT_MAX);
foreach (WC()->mailer()->get_emails() as $email) {
    add_filter('woocommerce_email_enabled_' . $email->id, '__return_false', PHP_INT_MAX);
}
global $wpdb;
if ((int)$wpdb->get_var("SELECT GET_LOCK('rootedops_ecwid_history_import', 10)") !== 1) {
    throw new RuntimeException('Another history import is running');
}
$result = array();
try {
    $existing = array();
    $page = 1;
    do {
        $found = wc_get_orders(array('type' => 'shop_order', 'limit' => 100, 'page' => $page++,
            'paginate' => true, 'status' => array_keys(wc_get_order_statuses())));
        foreach ($found->orders as $candidate) {
            $key = $candidate->get_meta('_rootedops_ecwid_history_key', true);
            if (!$key) continue;
            if (isset($existing[$key])) throw new RuntimeException('Duplicate history source key');
            $existing[$key] = $candidate;
        }
    } while ($page <= $found->max_num_pages);
    foreach ($input['orders'] as $plan) {
        $fingerprint = hash('sha256', wp_json_encode($plan, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
        if (isset($existing[$plan['source_key']])) {
            $order = $existing[$plan['source_key']];
            if ($order->get_meta('_rootedops_ecwid_history_hash', true) !== $fingerprint
                || wc_format_decimal($order->get_total(), 2) !== wc_format_decimal($plan['total'], 2)
                || $order->get_status() !== $plan['status'] || $order->get_currency() !== $plan['currency']
                || $order->get_customer_id() !== (int)$plan['woo_customer_id']) {
                throw new RuntimeException('Existing historical order differs from reviewed source');
            }
            $result[] = array('source_id' => $plan['id'], 'woo_id' => $order->get_id(), 'result' => 'reused');
            continue;
        }
        wc_transaction_query('start');
        try {
            $order = new WC_Order();
            $order->set_created_via('rootedops-ecwid-history');
            $order->set_customer_id($plan['woo_customer_id']);
            $order->set_currency($plan['currency']);
            $order->set_prices_include_tax(false);
            $order->set_date_created($plan['created']);
            $order->set_status($plan['status']);
            $order->set_date_paid(null);
            $order->set_date_completed(null);
            $order->set_payment_method('ecwid_history');
            $order->set_payment_method_title($plan['payment_method'] ?: 'Ecwid historical payment');
            $person = $plan['person'];
            $names = explode(' ', trim($person['name'] ?? ''), 2);
            $address = array('first_name' => $names[0] ?? '', 'last_name' => $names[1] ?? '',
                'company' => $person['companyName'] ?? '', 'address_1' => $person['street'] ?? '',
                'address_2' => '', 'city' => $person['city'] ?? '',
                'state' => $person['stateOrProvinceCode'] ?? '', 'postcode' => $person['postalCode'] ?? '',
                'country' => $person['countryCode'] ?? '', 'phone' => $person['phone'] ?? '');
            $order->set_address($address, 'shipping');
            $address['email'] = $plan['email'];
            $order->set_address($address, 'billing');
            foreach ($plan['lines'] as $line) {
                $item = new WC_Order_Item_Product();
                $item->set_name($line['name']);
                if ($line['woo_product_id']) $item->set_product(wc_get_product($line['woo_product_id']));
                $item->set_name($line['name']);
                $item->set_quantity($line['quantity']);
                $item->set_subtotal($line['gross']);
                $item->set_total($line['net']);
                $item->set_taxes(array('subtotal' => array(0 => $line['tax']), 'total' => array(0 => $line['tax'])));
                $item->add_meta_data('_ecwid_line_id', $line['id'], true);
                $item->add_meta_data('_ecwid_sku', $line['sku'], true);
                $item->add_meta_data('_ecwid_original_line_tax', $line['original_tax'], true);
                $order->add_item($item);
            }
            if ((float)$plan['shipping'] !== 0.0) {
                $shipping = new WC_Order_Item_Shipping();
                $shipping->set_method_title('Historical Ecwid shipping');
                $shipping->set_method_id('ecwid_history');
                $shipping->set_total($plan['shipping']);
                $order->add_item($shipping);
            }
            if ((float)$plan['tax'] !== 0.0) {
                $tax = new WC_Order_Item_Tax();
                $tax->set_rate_id(0);
                $tax->set_label('Historical Ecwid tax');
                $tax->set_tax_total($plan['tax']);
                $tax->set_shipping_tax_total(0);
                $order->add_item($tax);
            }
            $order->set_discount_total($plan['discount']);
            $order->set_discount_tax(0);
            $order->set_shipping_total($plan['shipping']);
            $order->set_shipping_tax(0);
            $order->set_cart_tax($plan['tax']);
            $order->set_total($plan['total']);
            $order->update_meta_data('_rootedops_ecwid_history_key', $plan['source_key']);
            $order->update_meta_data('_rootedops_ecwid_history_hash', $fingerprint);
            $order->update_meta_data('_rootedops_ecwid_payment_status', $plan['source_payment']);
            $order->update_meta_data('_rootedops_ecwid_fulfillment_status', $plan['source_fulfillment']);
            $order->update_meta_data('_rootedops_ecwid_reported_refund', $plan['reported_refund']);
            $order->update_meta_data('_rootedops_ecwid_order_id', $plan['id']);
            $order->update_meta_data('_rootedops_ecwid_tax_allocation', 'Order tax preserved; line allocation derived, not recalculated');
            $order->save();
            $order->get_data_store()->set_stock_reduced($order->get_id(), true);
            $saved = wc_get_order($order->get_id());
            if (wc_format_decimal($saved->get_total(), 2) !== wc_format_decimal($plan['total'], 2)
                || $saved->get_status() !== $plan['status'] || $saved->get_date_paid()) {
                throw new RuntimeException('Woo history readback mismatch');
            }
            wc_transaction_query('commit');
            $result[] = array('source_id' => $plan['id'], 'woo_id' => $saved->get_id(), 'result' => 'created');
        } catch (Throwable $error) {
            wc_transaction_query('rollback');
            throw $error;
        }
    }
    echo wp_json_encode($result);
} finally {
    $wpdb->get_var("SELECT RELEASE_LOCK('rootedops_ecwid_history_import')");
}
