<?php
// Executed by Docker PHP CLI in the *Dank Mushrooms staging* WP container.
// Writes exactly one Woo REST key and prints secret JSON to private subprocess pipe.
define('WP_USE_THEMES', false);
require '/var/www/html/wp-load.php';
if (parse_url(home_url(), PHP_URL_HOST) !== 'shop-test.danks.store') {
    fwrite(STDERR, "STOP: unexpected WordPress site\n"); exit(2);
}
if (!function_exists('wc_api_hash') || !function_exists('wc_get_product')) {
    fwrite(STDERR, "STOP: WooCommerce inactive\n"); exit(2);
}
global $wpdb;
$table = $wpdb->prefix . 'woocommerce_api_keys';
$description = 'RootedOps MP draft inventory staging (test shop only)';
$existing = $wpdb->get_var($wpdb->prepare(
    "SELECT COUNT(*) FROM `{$table}` WHERE description=%s", $description
));
if ($existing === null || intval($existing) !== 0) {
    fwrite(STDERR, "STOP: dedicated API key already exists or lookup failed\n"); exit(2);
}
$eligible = [];
foreach (get_users(['role' => 'administrator', 'fields' => 'ID']) as $id) {
    if (user_can($id, 'manage_woocommerce')) { $eligible[] = intval($id); }
}
if (count($eligible) !== 1) {
    fwrite(STDERR, "STOP: expected exactly one Woo administrator; choose user in Woo settings instead\n"); exit(2);
}
$key = 'ck_' . bin2hex(random_bytes(20));
$secret = 'cs_' . bin2hex(random_bytes(20));
$inserted = $wpdb->insert($table, [
    'user_id' => $eligible[0], 'description' => $description,
    'permissions' => 'read_write',
    'consumer_key' => wc_api_hash($key),
    'consumer_secret' => $secret,
    'truncated_key' => substr($key, -7),
], ['%d','%s','%s','%s','%s','%s']);
if ($inserted !== 1) {
    fwrite(STDERR, "STOP: Woo key insert failed\n"); exit(2);
}
echo wp_json_encode(['consumer_key' => $key, 'consumer_secret' => $secret, 'key_id' => $wpdb->insert_id]);
