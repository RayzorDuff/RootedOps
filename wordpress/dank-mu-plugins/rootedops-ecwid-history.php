<?php
/** Plugin Name: RootedOps Ecwid history guards */
defined('ABSPATH') || exit;

function rootedops_ecwid_historical_order($order) {
    if (is_numeric($order)) $order = wc_get_order($order);
    if ($order instanceof WC_Order_Refund) $order = wc_get_order($order->get_parent_id());
    return $order instanceof WC_Order && (bool) $order->get_meta('_rootedops_ecwid_history_key', true);
}

// History records describe source movements/payments; they never authorize new ones.
foreach (array('woocommerce_can_reduce_order_stock', 'woocommerce_can_restore_order_stock',
               'woocommerce_can_restock_refunded_items', 'woocommerce_order_needs_payment') as $hook) {
    add_filter($hook, static function ($allowed, $order) {
        return rootedops_ecwid_historical_order($order) ? false : $allowed;
    }, PHP_INT_MAX, 2);
}
add_filter('woocommerce_webhook_should_deliver', static function ($allowed, $webhook, $argument) {
    if (strpos($webhook->get_topic(), 'order.') === 0 && rootedops_ecwid_historical_order($argument)) return false;
    return $allowed;
}, PHP_INT_MAX, 3);

add_action('woocommerce_email', static function ($mailer) {
    foreach ($mailer->get_emails() as $email) {
        add_filter('woocommerce_email_enabled_' . $email->id, static function ($enabled, $object) {
            return rootedops_ecwid_historical_order($object) ? false : $enabled;
        }, PHP_INT_MAX, 2);
    }
});
