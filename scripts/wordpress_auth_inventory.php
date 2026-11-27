<?php
/**
 * RootedOps WordPress authentication inventory (read-only).
 * Run with PHP CLI from a WordPress container, never from the web server.
 * Does not print credentials, emails, option values, API tokens or cookies.
 */
if (PHP_SAPI !== 'cli') {
    http_response_code(403);
    exit;
}
$root = getenv('ROOTEDOPS_WP_ROOT') ?: '/var/www/html';
$bootstrap = rtrim($root, '/') . '/wp-load.php';
if (!is_file($bootstrap)) {
    fwrite(STDERR, "WordPress bootstrap not found\n");
    exit(2);
}
require_once $bootstrap;
if (!function_exists('get_option') || !function_exists('get_users')) {
    fwrite(STDERR, "WordPress bootstrap incomplete\n");
    exit(2);
}
$active = array_values(array_filter((array) get_option('active_plugins', []), 'is_string'));
$network = is_multisite() ? array_keys((array) get_site_option('active_sitewide_plugins', [])) : [];
$plugins = [];
foreach (array_unique(array_merge($active, $network)) as $plugin_file) {
    $file = WP_PLUGIN_DIR . '/' . $plugin_file;
    $headers = is_file($file) ? get_file_data($file, ['Name' => 'Plugin Name', 'Version' => 'Version']) : [];
    $plugins[] = [
        'basename' => $plugin_file,
        'name' => (string) ($headers['Name'] ?? ''),
        'version' => (string) ($headers['Version'] ?? ''),
        'network_active' => in_array($plugin_file, $network, true),
    ];
}
usort($plugins, static fn($a, $b) => strcmp($a['basename'], $b['basename']));
$roles = wp_roles()->get_names();
$role_counts = count_users()['avail_roles'] ?? [];
$role_summary = [];
foreach ($roles as $slug => $label) {
    $role_summary[$slug] = ['label' => $label, 'count' => (int) ($role_counts[$slug] ?? 0)];
}
ksort($role_summary);
$board_users = [];
foreach (get_users(['role' => 'board_director', 'fields' => ['ID'], 'number' => 200]) as $user) {
    $board_users[] = (int) $user->ID;
}
sort($board_users, SORT_NUMERIC);
// Only option names, not values: OAuth credentials commonly live in wp_options.
$auth_option_keys = [];
global $wpdb;
$keys = $wpdb->get_col("SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE '%oauth%' OR option_name LIKE '%openid%' OR option_name LIKE '%miniorange%' OR option_name LIKE '%saml%' OR option_name LIKE '%login%' ORDER BY option_name LIMIT 100");
foreach ((array) $keys as $key) {
    if (is_string($key)) {
        $auth_option_keys[] = $key;
    }
}
$pages = [];
foreach (['/board/', '/my-account/', '/checkout/'] as $path) {
    $page = get_page_by_path(trim($path, '/'));
    $pages[$path] = $page ? ['id' => (int) $page->ID, 'status' => $page->post_status] : null;
}
$report = [
    'schema' => 'rootedops-wordpress-auth-inventory-v1',
    'site_url_host' => (string) (wp_parse_url(site_url(), PHP_URL_HOST) ?: ''),
    'wp_version' => get_bloginfo('version'),
    'multisite' => is_multisite(),
    'woocommerce_active' => class_exists('WooCommerce'),
    'plugins' => $plugins,
    'role_summary' => $role_summary,
    'board_director_user_ids' => $board_users,
    'board_user_list_truncated' => count($board_users) === 200,
    'auth_option_names_only' => $auth_option_keys,
    'known_page_paths' => $pages,
    'board_library_auth_function_present' => function_exists('rp_board_library_authorized'),
];
echo wp_json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
