<?php
if (!defined('WP_CLI') || !WP_CLI || getenv('COMMERCE_NATIVE_WOO_FIXTURE') !== '1'
    || untrailingslashit(get_option('home')) !== 'http://127.0.0.1:8100') {
    throw new RuntimeException('Disposable Woo fixture only');
}
add_filter('home_url', static function () { return 'https://dankmushrooms.net'; });
function history_ci_require($condition, $message) {
    if (!$condition) throw new RuntimeException($message);
}
function history_ci_import($plans) {
    $input = array('action' => 'apply', 'orders' => $plans);
    ob_start();
    include __DIR__ . '/commerce_history_woo.php';
    return json_decode(ob_get_clean(), true, 512, JSON_THROW_ON_ERROR);
}
$product = new WC_Product_Simple();
$product->set_name('Synthetic historical merchandise');
$product->set_manage_stock(true);
$product->set_stock_quantity(7);
$product->set_regular_price('14.95');
$product->save();
$source = 'synthetic-history-' . wp_generate_uuid4();
$line = array('id' => 'line', 'sku' => 'old-synthetic', 'name' => 'Historical name',
    'quantity' => '2', 'gross' => '29.90', 'net' => '29.90', 'tax' => '1.91',
    'original_tax' => 1.92, 'woo_product_id' => $product->get_id());
$plan = array('id' => $source, 'source_key' => $source, 'currency' => 'USD',
    'created' => '2025-01-01T00:00:00+00:00', 'status' => 'completed',
    'woo_customer_id' => 1, 'payment_method' => 'Historical cash', 'person' => array(),
    'email' => 'synthetic@example.invalid', 'lines' => array($line), 'shipping' => '0.00',
    'discount' => '0.00', 'tax' => '1.91', 'total' => '31.81', 'reported_refund' => '0',
    'source_payment' => 'PAID', 'source_fulfillment' => 'DELIVERED');
$unpaid = $plan;
$unpaid['id'] .= '-unpaid';
$unpaid['source_key'] .= '-unpaid';
$unpaid['source_payment'] = 'AWAITING_PAYMENT';
$unpaid['woo_customer_id'] = 0;
$unpaid['status'] = 'on-hold';
$unpaid['total'] = '30.91';
$unpaid['discount'] = '0.90';
$unpaid['lines'][0]['net'] = '29.00';
$first = history_ci_import(array($plan, $unpaid));
$second = history_ci_import(array($plan, $unpaid));
history_ci_require(count($first) === 2 && array_column($first, 'woo_id') === array_column($second, 'woo_id'), 'Retry duplicated orders');
$paid = wc_get_order($first[0]['woo_id']);
$open = wc_get_order($first[1]['woo_id']);
history_ci_require(wc_format_decimal($paid->get_total(), 2) === '31.81' && wc_format_decimal($paid->get_total_tax(), 2) === '1.91', 'Historical total/tax changed');
history_ci_require(!$paid->get_date_paid(), 'Invented paid timestamp');
history_ci_require($open->get_status() === 'on-hold' && !$open->is_paid(), 'Unpaid source became paid');
history_ci_require($open->get_customer_id() === 0 && $open->get_billing_email() === 'synthetic@example.invalid', 'Named guest identity changed');
history_ci_require(wc_format_decimal($open->get_discount_total(), 2) === '0.90', 'Discount changed');
history_ci_require((int)wc_get_product($product->get_id())->get_stock_quantity() === 7, 'Import changed stock');
// Remove the request-wide suppression to check the permanent history guards.
foreach (array('woocommerce_can_reduce_order_stock', 'woocommerce_can_restore_order_stock',
               'woocommerce_can_restock_refunded_items') as $hook) {
    remove_filter($hook, '__return_false', PHP_INT_MAX);
}
$open->update_status('pending');
history_ci_require(!$open->needs_payment(), 'Historical order became payable');
$open->update_status('cancelled');
history_ci_require((int)wc_get_product($product->get_id())->get_stock_quantity() === 7, 'Historical cancellation restored stock');
remove_filter('woocommerce_webhook_should_deliver', '__return_false', PHP_INT_MAX);
$hook = new WC_Webhook();
$hook->set_topic('order.updated');
history_ci_require(!apply_filters('woocommerce_webhook_should_deliver', true, $hook, $open->get_id()), 'Historical update generated a live webhook');
foreach ($first as $row) wc_get_order($row['woo_id'])->delete(true);
$product->delete(true);
echo "Native Woo history: totals, tax, discounts, retry, unpaid status and stock guards passed\n";
