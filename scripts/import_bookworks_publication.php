<?php
/**
 * Reusable BookWorks publication importer. CLI only, invoked within WordPress container.
 * Payload is a JSON file in /tmp, staged by the wrapper; no HTTP endpoint.
 */
if (PHP_SAPI !== 'cli') { exit(1); }
require '/var/www/html/wp-load.php';

function fail_import($message) { fwrite(STDERR, $message . "\n"); exit(1); }
if ($argc !== 3 || !in_array($argv[2], ['dry-run', 'draft'], true)) {
    fail_import('Usage: php import_bookworks_publication.php /tmp/payload.json dry-run|draft');
}
$payload = json_decode(file_get_contents($argv[1]), true);
if (!is_array($payload)) fail_import('Invalid JSON payload');
foreach (['publication_id', 'profile', 'source_commit', 'title', 'slug', 'html'] as $key) {
    if (!isset($payload[$key]) || !is_string($payload[$key]) || trim($payload[$key]) === '') {
        fail_import('Missing field: ' . $key);
    }
}
if (!preg_match('/^[a-z0-9][a-z0-9-]{1,120}$/', $payload['publication_id'])
    || !preg_match('/^[a-z0-9][a-z0-9-]{0,80}$/', $payload['profile'])
    || !preg_match('/^[0-9a-f]{40}$/', $payload['source_commit'])
    || !preg_match('/^[a-z0-9][a-z0-9-]{0,180}$/', $payload['slug'])) {
    fail_import('Invalid publication id, profile, commit or slug');
}
$key = $payload['publication_id'] . ':' . $payload['profile'];
$matches = get_posts([
    'post_type' => 'page', 'post_status' => 'any', 'numberposts' => -1,
    'meta_key' => '_bookworks_publication_key', 'meta_value' => $key,
]);
if (count($matches) > 1) fail_import('Duplicate WordPress pages with BookWorks key; manual resolution required');
$page = $matches ? $matches[0] : null;
$slug_owner = get_page_by_path($payload['slug'], OBJECT, 'page');
if ($slug_owner && (!$page || (int)$slug_owner->ID !== (int)$page->ID)) {
    fail_import('Slug is already owned by another WordPress page');
}
// Normalize through WordPress before comparing, so Pandoc's unsupported attributes
// do not prevent a safe draft import or cause false changes on repeated runs.
$html = wp_kses_post($payload['html']);
if (trim(wp_strip_all_tags($html)) === '') fail_import('No usable content after sanitization');
$source_hash = hash('sha256', $html);
$last_hash = $page ? get_post_meta($page->ID, '_bookworks_managed_html_sha256', true) : '';
if ($page && $last_hash && !hash_equals($last_hash, hash('sha256', $page->post_content))) {
    fail_import('WordPress page was manually edited after last import; refusing overwrite');
}
if ($page && !$last_hash) fail_import('Existing managed page lacks content hash; refusing overwrite');
$unchanged = $page && hash_equals($source_hash, $last_hash);
$action = !$page ? 'create-draft' : ($unchanged ? 'unchanged' : 'update-draft');
echo json_encode(['action' => $action, 'key' => $key, 'page_id' => $page ? (int)$page->ID : null,
    'source_commit' => $payload['source_commit'], 'sha256' => $source_hash], JSON_PRETTY_PRINT) . "\n";
if ($argv[2] === 'dry-run' || $unchanged) exit(0);
// This adapter intentionally NEVER publishes a page or edits homepage/menu settings.
// The sanitized HTML above is the content that WordPress will store.
$args = [
    'post_type' => 'page', 'post_title' => $payload['title'],
    'post_name' => $payload['slug'], 'post_content' => wp_slash($html), 'post_status' => 'draft',
];
if ($page) $args['ID'] = $page->ID;
$id = wp_insert_post($args, true);
if (is_wp_error($id)) fail_import($id->get_error_message());
update_post_meta($id, '_bookworks_publication_key', $key);
update_post_meta($id, '_bookworks_source_commit', $payload['source_commit']);
$saved = get_post($id);
update_post_meta($id, '_bookworks_managed_html_sha256', hash('sha256', $saved->post_content));
echo "Staged draft WordPress page ID $id; publication requires manual approval.\n";
