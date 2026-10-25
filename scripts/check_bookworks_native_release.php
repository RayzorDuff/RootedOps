<?php
/** Read-only verification of a managed native BookWorks publication. */
if (PHP_SAPI !== 'cli') exit(1);
require '/var/www/html/wp-load.php';
function bw_check_fail($msg) { fwrite(STDERR, $msg . "\n"); exit(1); }
if ($argc !== 2) bw_check_fail('Usage: php check_bookworks_native_release.php wordpress.json');
$payload = json_decode(file_get_contents($argv[1]), true);
if (!is_array($payload)) bw_check_fail('Invalid payload');
$key = ($payload['publication_id'] ?? '') . ':' . ($payload['profile'] ?? '');
$pages = get_posts(['post_type'=>'page','post_status'=>'any','numberposts'=>-1,
    'meta_key'=>'_bookworks_publication_key','meta_value'=>$key]);
if (count($pages) !== 1) bw_check_fail('Expected exactly one managed page');
$page = $pages[0];
if ($page->post_name !== ($payload['slug'] ?? '') || !in_array($page->post_status, ['draft','publish'], true))
    bw_check_fail('Page slug or status mismatch');
$stored = get_post_meta($page->ID, '_bookworks_managed_html_sha256', true);
$actual = hash('sha256', $page->post_content);
if (!is_string($stored) || !hash_equals($stored, $actual)) bw_check_fail('Managed page checksum mismatch');
$roles = get_post_meta($page->ID, '_bookworks_media_roles', true);
if (!is_array($roles)) $roles = [];
foreach ($roles as $role => $id) {
    if (!wp_attachment_is_image((int)$id)) bw_check_fail('Invalid media attachment: ' . $role);
}
$css = WP_CONTENT_DIR . '/mu-plugins/bookworks-fundraising.css';
$loader = WP_CONTENT_DIR . '/mu-plugins/bookworks-fundraising-loader.php';
if (($payload['layout'] ?? '') === 'fundraising-landing' && (!is_file($css) || !is_file($loader)))
    bw_check_fail('Fundraising presentation assets missing');
echo wp_json_encode(['action'=>'verified','page_id'=>$page->ID,'status'=>$page->post_status,
    'key'=>$key,'source_commit'=>get_post_meta($page->ID,'_bookworks_source_commit',true),
    'managed_sha256'=>$actual,'media_roles'=>$roles,'fundraising_styles_present'=>is_file($css)],
    JSON_PRETTY_PRINT) . "\n";
