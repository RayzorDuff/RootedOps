<?php
/** Read-only official Clover WooCommerce plugin and gateway preflight. No secrets output. */
define('WP_USE_THEMES', false);
require '/var/www/html/wp-load.php';

$expected = 'shop-test.danks.store';
$host = parse_url(home_url(), PHP_URL_HOST);
if ($host !== $expected) {
    fwrite(STDERR, "STOP: wrong WordPress host\n");
    exit(2);
}
if (!class_exists('WooCommerce') || !function_exists('WC')) {
    fwrite(STDERR, "STOP: WooCommerce not active\n");
    exit(2);
}
require_once ABSPATH . 'wp-admin/includes/plugin.php';
$installed = get_plugins();
$matches = [];
foreach ($installed as $slug => $meta) {
    $title = (string)($meta['Name'] ?? '');
    if (stripos($slug, 'clover') === false && stripos($title, 'clover') === false) continue;
    $matches[] = [
        'slug' => $slug,
        'name' => $title,
        'version' => (string)($meta['Version'] ?? 'unknown'),
        'active' => is_plugin_active($slug)
    ];
}
$gateways = [];
foreach (WC()->payment_gateways()->payment_gateways() as $id => $gateway) {
    $class = get_class($gateway);
    if (stripos($id, 'clover') === false && stripos($class, 'clover') === false) continue;
    $cfg = is_array($gateway->settings ?? null) ? $gateway->settings : [];
    $fields = [];
    foreach ($cfg as $key => $value) {
        if (!preg_match('/(merchant|public|private|token|key|secret)/i', (string)$key)) continue;
        $fields[(string)$key] = is_scalar($value) && trim((string)$value) !== '' ? 'configured' : 'missing';
    }
    $gateways[] = [
        'id' => (string)$id,
        'class' => $class,
        'enabled' => (string)($gateway->enabled ?? 'unknown'),
        'environment' => (string)($cfg['environment'] ?? $cfg['mode'] ?? 'not identified'),
        'credential_fields' => $fields
    ];
}
$output = [
    'site' => $host,
    'wordpress_version' => get_bloginfo('version'),
    'woocommerce_version' => defined('WC_VERSION') ? WC_VERSION : 'unknown',
    'clover_plugins' => $matches,
    'clover_gateways' => $gateways,
    'payments_mutated' => false,
];
echo wp_json_encode($output, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), "\n";
