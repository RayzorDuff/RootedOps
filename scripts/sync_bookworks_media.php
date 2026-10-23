<?php
/** BookWorks managed-media importer; CLI only. Never publishes or edits post_content. */
if (PHP_SAPI !== 'cli') { exit(1); }
require '/var/www/html/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/image.php';
require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/media.php';
function media_fail($message) { fwrite(STDERR, $message . "\n"); exit(1); }
if ($argc !== 4 || !in_array($argv[3], ['check', 'stage'], true)) {
    media_fail('Usage: php sync_bookworks_media.php manifest.json asset-directory check|stage');
}
$manifest = json_decode(file_get_contents($argv[1]), true);
if (!is_array($manifest) || ($manifest['schema_version'] ?? null) !== 1) media_fail('Invalid media manifest');
$key = $manifest['publication_key'] ?? '';
if (!is_string($key) || !preg_match('/^[a-z0-9-]+:[a-z0-9-]+$/', $key)) media_fail('Invalid publication key');
$assets = $manifest['assets'] ?? null;
if (!is_array($assets) || !$assets || count($assets) > 30) media_fail('Expected 1-30 media assets');
$pages = get_posts(['post_type'=>'page','post_status'=>'any','numberposts'=>-1,
    'meta_key'=>'_bookworks_publication_key','meta_value'=>$key]);
if (count($pages) !== 1) media_fail('Expected exactly one managed page for publication key');
$page = $pages[0];
if ($argv[3] === 'stage' && $page->post_status !== 'draft') {
    media_fail('Media staging is restricted to drafts; published page requires reviewed revision workflow');
}
$roles = [];
$plans = [];
foreach ($assets as $asset) {
    if (!is_array($asset)) media_fail('Invalid asset');
    $role = $asset['role'] ?? '';
    $filename = $asset['filename'] ?? '';
    $sha = $asset['sha256'] ?? '';
    $mime = $asset['mime'] ?? '';
    $alt = $asset['alt'] ?? '';
    $caption = $asset['caption'] ?? '';
    if (!is_string($role) || !preg_match('/^[a-z][a-z0-9-]{0,50}$/', $role) || isset($roles[$role])) media_fail('Invalid or duplicate media role');
    $roles[$role] = true;
    if (!is_string($filename) || !preg_match('/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,160}$/', $filename) || strpos($filename, '..') !== false) media_fail('Invalid filename');
    if (!is_string($sha) || !preg_match('/^[a-f0-9]{64}$/', $sha)) media_fail('Invalid checksum');
    if (!in_array($mime, ['image/jpeg','image/png','image/webp'], true)) media_fail('Unsupported MIME');
    if (!is_string($alt) || trim($alt) === '' || !is_string($caption) || trim($caption) === '') media_fail('Alt and caption required');
    $path = rtrim($argv[2], '/') . '/' . $filename;
    if (!is_file($path) || !hash_equals($sha, hash_file('sha256', $path))) media_fail('Missing asset or SHA mismatch: ' . $filename);
    $actual_mime = wp_check_filetype_and_ext($path, $filename)['type'] ?? null;
    if ($actual_mime !== $mime) media_fail('MIME mismatch: ' . $filename);
    $found = get_posts(['post_type'=>'attachment','post_status'=>'inherit','numberposts'=>-1,
        'meta_key'=>'_bookworks_media_sha256','meta_value'=>$sha]);
    if (count($found) > 1) media_fail('Duplicate managed attachments for checksum');
    $existing_id = $found ? (int)$found[0]->ID : null;
    $plans[] = compact('role','filename','sha','mime','alt','caption','path','existing_id');
}
if ($argv[3] === 'check') {
    echo json_encode(['action'=>'check','publication_key'=>$key,'page_id'=>$page->ID,
        'status'=>$page->post_status,'assets'=>array_map(function($a) {
            return ['role'=>$a['role'],'filename'=>$a['filename'],'attachment_id'=>$a['existing_id'],
                'action'=>$a['existing_id'] ? 'reuse' : 'upload'];
        }, $plans)], JSON_PRETTY_PRINT) . "\n";
    exit(0);
}
$ids = [];
foreach ($plans as $asset) {
    $id = $asset['existing_id'];
    if (!$id) {
        $upload = wp_upload_bits($asset['filename'], null, file_get_contents($asset['path']));
        if (!empty($upload['error'])) media_fail('Upload failed: ' . $upload['error']);
        $id = wp_insert_attachment(['post_mime_type'=>$asset['mime'],
            'post_title'=>pathinfo($asset['filename'], PATHINFO_FILENAME),
            'post_status'=>'inherit'], $upload['file'], 0, true);
        if (is_wp_error($id)) media_fail($id->get_error_message());
        wp_update_attachment_metadata($id, wp_generate_attachment_metadata($id, $upload['file']));
        update_post_meta($id, '_bookworks_media_sha256', $asset['sha']);
    }
    if (!wp_attachment_is_image($id)) media_fail('Attachment is not an image');
    wp_update_post(['ID'=>$id,'post_excerpt'=>$asset['caption']]);
    update_post_meta($id, '_wp_attachment_image_alt', $asset['alt']);
    $ids[$asset['role']] = $id;
}
// Generic, namespaced role map; adapters can consume it without editing managed HTML.
update_post_meta($page->ID, '_bookworks_media_roles', $ids);
echo json_encode(['action'=>'staged-media','publication_key'=>$key,'page_id'=>$page->ID,
    'status'=>$page->post_status,'attachments'=>$ids], JSON_PRETTY_PRINT) . "\n";
