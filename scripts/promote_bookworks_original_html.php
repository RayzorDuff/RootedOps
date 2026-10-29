<?php
/** CLI-only: inspect/adopt a published WordPress shortcode page. HTML installation is handled separately. */
if (PHP_SAPI !== 'cli') exit(1);
require '/var/www/html/wp-load.php';
function fail_bw($message) { fwrite(STDERR, $message . "\n"); exit(1); }
if ($argc !== 5 || !in_array($argv[4], ['check','adopt','record'], true)) fail_bw('Usage: php promote_bookworks_original_html.php KEY SLUG SHA256 check|adopt|record');
[$script,$key,$slug,$hash,$mode] = $argv;
if (!preg_match('/^[a-z0-9-]+:[a-z0-9-]+$/', $key) ||
    !preg_match('/^[a-z0-9-]+$/', $slug) ||
    !preg_match('/^[a-f0-9]{64}$/', $hash)) fail_bw('Invalid arguments');
$path = '/var/www/html/bookworks/' . $slug . '.html';
$owner = get_page_by_path($slug, OBJECT, 'page');
if (!$owner || $owner->post_status !== 'publish') fail_bw('Expected one published page at slug');
$expected = '[bookworks_publication file="' . $slug . '.html"]';
if (trim($owner->post_content) !== $expected) fail_bw('Page content differs from managed shortcode; refusing');
$matches = get_posts(['post_type'=>'page','post_status'=>'any','numberposts'=>-1,'meta_key'=>'_bookworks_original_key','meta_value'=>$key]);
// Trashed predecessors must not prevent adopting a replacement page. Never adopt if another non-trashed page owns the key.
$active_matches = array_values(array_filter($matches, function($p) { return !in_array($p->post_status, ['trash', 'auto-draft'], true); }));
if (count($active_matches) > 1 || ($active_matches && (int)$active_matches[0]->ID !== (int)$owner->ID)) fail_bw('Managed key conflict');
$existing = get_post_meta($owner->ID, '_bookworks_original_key', true);
if ($existing && $existing !== $key) fail_bw('Page managed by another publication');
if ($mode === 'record' && !$existing) fail_bw('Adopt the page first');
if ($mode === 'record' && (!is_file($path) || hash_file('sha256',$path) !== $hash)) fail_bw('Installed HTML hash mismatch');
echo json_encode(['page_id'=>$owner->ID,'slug'=>$slug,'status'=>$owner->post_status,'managed_key'=>$existing ?: null,'mode'=>$mode]) . "\n";
if ($mode === 'adopt' && !$existing) {
    update_post_meta($owner->ID, '_bookworks_original_key', $key);
    echo "Adopted published page " . $owner->ID . "\n";
}
if ($mode === 'record') {
    update_post_meta($owner->ID, '_bookworks_original_html_sha256', $hash);
    update_post_meta($owner->ID, '_bookworks_original_promoted_at', gmdate('c'));
}
