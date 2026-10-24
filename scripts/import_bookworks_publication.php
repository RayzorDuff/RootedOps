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
// Apply theme presentation settings even when imported content is unchanged.
function ensure_public_edition_css($page_id) {
    $rule = 'body.page-id-' . (int)$page_id . ' .wp-block-post-title, body.page-id-' . (int)$page_id . ' h1.entry-title { display: none !important; }';
    $existing_css = wp_get_custom_css();
    if (strpos($existing_css, $rule) === false) {
        $updated_css = wp_update_custom_css_post(trim($existing_css . "\n" . $rule));
        if (is_wp_error($updated_css)) fail_import('Could not save page-scoped title CSS: ' . $updated_css->get_error_message());
    }
}
// Normalize through WordPress before comparing, so Pandoc's unsupported attributes
// do not prevent a safe draft import or cause false changes on repeated runs.
// Resolve only explicit managed image roles, after media has been staged to this draft.
// An unresolved role remains a harmless HTML comment until the second stage pass.
$raw_html = $payload['html'];
if (($payload['layout'] ?? '') === 'public-edition') {
    // The WordPress page title and the illustrated cover already carry the
    // publication identity. Avoid repeating the BookWorks subtitle below it.
    $raw_html = preg_replace('~<header class="bookworks-hero">.*?</header>~s', '', $raw_html, 1);
    $role_map = $page ? get_post_meta($page->ID, '_bookworks_media_roles', true) : [];
    if (!is_array($role_map)) $role_map = [];
    foreach (['cover', 'chapter-01', 'chapter-02', 'chapter-03', 'chapter-04', 'chapter-05'] as $role) {
        $marker = '<!-- bookworks-media:' . $role . ' -->';
        if (isset($role_map[$role])) {
            $id = (int)$role_map[$role];
            if (!wp_attachment_is_image($id) || get_post_meta($id, '_bookworks_media_sha256', true) === '') {
                fail_import('Unmanaged or invalid media attachment for role ' . $role);
            }
            $alt = get_post_meta($id, '_wp_attachment_image_alt', true);
            $url = wp_get_attachment_url($id);
            if (!$url) fail_import('Missing URL for media role ' . $role);
            $cover_style = ' style="max-width: 520px; width: 100%; height: auto; margin: 0 auto 2rem;"';
            $image_style = ' style="display: block; max-width: 100%; height: auto;"';
            $figure = '<figure class="bookworks-media bookworks-media-' . esc_attr($role) . '"' . $cover_style . '><img src="' . esc_url($url) . '" alt="' . esc_attr($alt) . '"' . $image_style . ' /></figure>';
            $raw_html = str_replace($marker, $figure, $raw_html);
        }
    }
}
$html = wp_kses_post($raw_html);
// Only the known, media-free landing-page schema is supported here. Asset
// synchronization requires a separate reviewed importer change.
if (isset($payload['schema_version']) && $payload['schema_version'] !== 1) {
    fail_import('Unsupported BookWorks package schema');
}
if (!empty($payload['media'])) {
    fail_import('Media manifest is not supported by this importer yet');
}
if (isset($payload['html_sha256']) && !hash_equals($payload['html_sha256'], hash('sha256', $payload['html']))) {
    fail_import('BookWorks HTML checksum mismatch');
}
if (trim(wp_strip_all_tags($html)) === '') fail_import('No usable content after sanitization');
$source_hash = hash('sha256', $html);
$last_hash = $page ? get_post_meta($page->ID, '_bookworks_managed_html_sha256', true) : '';
if ($page && $last_hash && !hash_equals($last_hash, hash('sha256', $page->post_content))) {
    fail_import('WordPress page was manually edited after last import; refusing overwrite');
}
if ($page && !$last_hash) fail_import('Existing managed page lacks content hash; refusing overwrite');
// Published content requires a separately reviewed update/republication process.
// Never let a draft deployment silently unpublish a live page.
$unchanged = $page && hash_equals($source_hash, $last_hash);
if ($page && $page->post_status === 'publish' && !$unchanged) {
    fail_import('Managed page is published; refusing to overwrite or unpublish it. Create a reviewed revision workflow.');
}
if ($page && !in_array($page->post_status, ['draft', 'publish'], true)) {
    fail_import('Unsupported existing page status; refusing mutation');
}
$action = !$page ? 'create-draft' : ($unchanged ? 'unchanged' : 'update-draft');
echo json_encode(['action' => $action, 'key' => $key, 'page_id' => $page ? (int)$page->ID : null,
    'source_commit' => $payload['source_commit'], 'sha256' => $source_hash], JSON_PRETTY_PRINT) . "\n";
if ($argv[2] === 'dry-run') exit(0);
if ($unchanged) {
    if (($payload['layout'] ?? '') === 'public-edition') ensure_public_edition_css($page->ID);
    exit(0);
}
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
if (($payload['layout'] ?? '') === 'public-edition') ensure_public_edition_css($id);
update_post_meta($id, '_bookworks_source_commit', $payload['source_commit']);
$saved = get_post($id);
update_post_meta($id, '_bookworks_managed_html_sha256', hash('sha256', $saved->post_content));
echo "Staged draft WordPress page ID $id; publication requires manual approval.\n";
