<?php
/** CLI-only: create an unpublished shortcode page for an approved static BookWorks document. */
if (PHP_SAPI !== 'cli') exit(1);
require '/var/www/html/wp-load.php';
function bw_fail($message) { fwrite(STDERR, $message . "\n"); exit(1); }
if ($argc !== 4 || !in_array($argv[3], ['check','stage'], true)) bw_fail('Usage: php stage_bookworks_original_html.php KEY SLUG check|stage');
$key = $argv[1]; $slug = $argv[2]; $mode = $argv[3];
if (!preg_match('/^[a-z0-9-]+:[a-z0-9-]+$/', $key) || !preg_match('/^[a-z0-9-]+$/', $slug)) bw_fail('Invalid key or slug');
$file = $slug . '.html';
$path = '/var/www/html/bookworks/' . $file;
if (!is_file($path)) bw_fail('Missing deployed HTML: ' . $path);
if (!is_file(WP_PLUGIN_DIR . '/bookworks-original-html/bookworks-original-html.php')) bw_fail('Renderer plugin not installed');
if (!is_plugin_active('bookworks-original-html/bookworks-original-html.php')) {
    require_once ABSPATH . 'wp-admin/includes/plugin.php';
    if (!is_plugin_active('bookworks-original-html/bookworks-original-html.php')) bw_fail('Renderer plugin not active');
}
$matches = get_posts(['post_type'=>'page','post_status'=>'any','numberposts'=>-1,'meta_key'=>'_bookworks_original_key','meta_value'=>$key]);
if (count($matches)>1) bw_fail('Duplicate managed pages');
$page = $matches ? $matches[0] : null;
$owner = get_page_by_path($slug, OBJECT, 'page');
if ($owner && (!$page || $owner->ID !== $page->ID)) bw_fail('Slug already belongs to another page');
if ($page && $page->post_status !== 'draft') bw_fail('Refusing to modify non-draft page');
$content = '[bookworks_publication file="' . $file . '"]';
if ($page && $page->post_content !== $content) bw_fail('Managed draft was edited manually; refusing overwrite');
echo json_encode(['action'=>$page?'unchanged':'create-draft','key'=>$key,'slug'=>$slug,'mode'=>$mode]) . "\n";
if ($mode === 'check' || $page) exit(0);
$id = wp_insert_post(['post_type'=>'page','post_status'=>'draft','post_title'=>ucwords(str_replace('-',' ',$slug)),'post_name'=>$slug,'post_content'=>$content], true);
if (is_wp_error($id)) bw_fail($id->get_error_message());
update_post_meta($id,'_bookworks_original_key',$key);
echo "Created draft page $id (never published)\n";
