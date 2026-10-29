<?php
/** Explicit one-time conversion of a BookWorks iframe draft into a native draft. CLI only. */
if (PHP_SAPI !== 'cli') exit(1);
require '/var/www/html/wp-load.php';
function conversion_fail($message) { fwrite(STDERR, $message . "\n"); exit(1); }
if ($argc !== 4 || !in_array($argv[3], ['check','convert'], true)) {
    conversion_fail('Usage: php convert_bookworks_original_draft.php approved-wordpress.json PAGE_ID check|convert');
}
$payload = json_decode(file_get_contents($argv[1]), true);
if (!is_array($payload)) conversion_fail('Invalid WordPress payload');
foreach (['publication_id','profile','slug','title','html','html_sha256','source_commit'] as $field) {
    if (!isset($payload[$field]) || !is_string($payload[$field])) conversion_fail('Missing payload field: ' . $field);
}
if (($payload['schema_version'] ?? null) !== 1 || ($payload['layout'] ?? '') !== 'fundraising-landing'
    || ($payload['media'] ?? null) !== [] || !preg_match('/^[a-f0-9]{40}$/', $payload['source_commit'])
    || !preg_match('/^[a-f0-9]{64}$/', $payload['html_sha256'])
    || !hash_equals($payload['html_sha256'], hash('sha256', $payload['html']))) conversion_fail('Invalid native payload integrity');
$key = $payload['publication_id'] . ':' . $payload['profile'];
if (!preg_match('/^[a-z0-9-]+:[a-z0-9-]+$/', $key)
    || !preg_match('/^[a-z0-9-]+$/', $payload['slug'])) conversion_fail('Invalid identity');
$id = filter_var($argv[2], FILTER_VALIDATE_INT, ['options'=>['min_range'=>1]]);
if (!$id) conversion_fail('Invalid page ID');
$page = get_post($id);
if (!$page || $page->post_type !== 'page' || $page->post_status !== 'draft'
    || $page->post_name !== $payload['slug']) conversion_fail('Page is not the expected draft and slug');
if (get_post_meta($id, '_bookworks_original_key', true) !== $key) conversion_fail('Original management key mismatch');
if (metadata_exists('post', $id, '_bookworks_publication_key')) conversion_fail('Page already has native ownership metadata');
$matches = get_posts(['post_type'=>'page','post_status'=>'any','numberposts'=>-1,
    'meta_key'=>'_bookworks_publication_key','meta_value'=>$key]);
if ($matches) conversion_fail('Native publication key already exists');
$expected_shortcode = '[bookworks_publication file="' . $payload['slug'] . '.html"]';
if (trim($page->post_content) !== $expected_shortcode) conversion_fail('Draft was edited or shortcode differs');
$native_html = wp_kses_post($payload['html']);
if (trim(wp_strip_all_tags($native_html)) === '') conversion_fail('Native HTML is empty');
echo json_encode(['action'=>$argv[3], 'page_id'=>$id, 'publication_key'=>$key,
    'source_commit'=>$payload['source_commit']], JSON_PRETTY_PRINT) . "\n";
if ($argv[3] === 'check') exit(0);
$backup = [
    'post_content'=>$page->post_content,
    'post_title'=>$page->post_title,
    'post_status'=>$page->post_status,
    'post_name'=>$page->post_name,
    'original_key'=>$key,
    'saved_at'=>gmdate('c'),
];
if (!add_post_meta($id, '_bookworks_native_conversion_backup', wp_json_encode($backup), true)) {
    conversion_fail('Conversion backup already exists; refusing repeat');
}
$updated = wp_update_post(['ID'=>$id, 'post_content'=>wp_slash($native_html),
    'post_title'=>$payload['title'], 'post_status'=>'draft'], true);
if (is_wp_error($updated) || (int)$updated !== (int)$id) conversion_fail('Failed to update draft; backup retained');
$saved = get_post($id);
if ($saved->post_status !== 'draft' || $saved->post_name !== $payload['slug']) conversion_fail('Post-update identity mismatch');
update_post_meta($id, '_bookworks_publication_key', $key);
update_post_meta($id, '_bookworks_source_commit', $payload['source_commit']);
update_post_meta($id, '_bookworks_managed_html_sha256', hash('sha256', $saved->post_content));
delete_post_meta($id, '_bookworks_original_key', $key);
echo "Converted existing draft page $id to WordPress-native BookWorks ownership; still unpublished.\n";
