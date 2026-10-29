<?php
/** Read-only pre-adoption inventory for Rooted Psyche's existing front page. */
if (PHP_SAPI !== 'cli') exit(1);
require '/var/www/html/wp-load.php';
$id = (int) get_option('page_on_front');
if (get_option('show_on_front') !== 'page' || !$id) {
    fwrite(STDERR, "WordPress does not have a static front page configured.\n");
    exit(1);
}
$page = get_post($id);
if (!$page || $page->post_type !== 'page') {
    fwrite(STDERR, "Invalid front-page post.\n"); exit(1);
}
$keys = ['_rootedpsyche_grav_imported', '_bookworks_publication_key', '_bookworks_managed_html_sha256', '_bookworks_source_commit'];
$meta = [];
foreach ($keys as $key) $meta[$key] = get_post_meta($id, $key, true);
$qr = get_posts(['post_type' => 'attachment', 'post_status' => 'inherit',
    'meta_key' => '_rootedpsyche_grav_qr', 'meta_value' => '1', 'posts_per_page' => -1]);
$menus = get_nav_menu_locations();
$report = [
    'mode' => 'read-only-inventory',
    'site_url' => home_url('/'),
    'page_on_front' => $id,
    'slug' => $page->post_name,
    'title' => $page->post_title,
    'status' => $page->post_status,
    'permalink' => get_permalink($id),
    'content_sha256' => hash('sha256', $page->post_content),
    'content_bytes' => strlen($page->post_content),
    'meta' => $meta,
    'qr_attachment_ids' => array_map(fn($p) => (int)$p->ID, $qr),
    'nav_menu_locations' => $menus,
    'givebutter_plugin_file_present' => file_exists(WP_CONTENT_DIR . '/mu-plugins/rootedpsyche-givebutter.php'),
    'givebutter_widget_id' => 'gJeP4L',
];
echo wp_json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
