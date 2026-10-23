<?php
if (PHP_SAPI !== 'cli') { exit(1); }
require '/var/www/html/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/image.php';
function rootedpsyche_import_brand_asset($file, $name) {
    if (!is_file($file) || !is_readable($file)) {
        throw new RuntimeException("Missing or unreadable asset: $file");
    }
    $bytes = file_get_contents($file);
    if ($bytes === false || strlen($bytes) < 100 || !getimagesizefromstring($bytes)) {
        throw new RuntimeException("Invalid image data: $file");
    }
    $prior = get_posts(['post_type'=>'attachment','post_status'=>'inherit','meta_key'=>'_rootedpsyche_brand_asset','meta_value'=>$name,'posts_per_page'=>1]);
    $id = $prior ? (int)$prior[0]->ID : 0;
    $existing_file = $id ? get_attached_file($id) : '';
    if ($id && $existing_file && is_file($existing_file) && filesize($existing_file) > 100) {
        return $id;
    }
    $upload = wp_upload_bits($name . '.png', null, $bytes);
    if (!empty($upload['error']) || empty($upload['file']) || !is_file($upload['file'])) {
        throw new RuntimeException($upload['error'] ?? 'Upload failed');
    }
    if ($id) {
        update_attached_file($id, $upload['file']);
    } else {
        $id = wp_insert_attachment(['post_mime_type'=>'image/png','post_title'=>'Rooted Psyche ' . $name,'post_status'=>'inherit'], $upload['file']);
        if (is_wp_error($id) || !$id) { throw new RuntimeException('Could not create attachment'); }
    }
    wp_update_attachment_metadata($id, wp_generate_attachment_metadata($id, $upload['file']));
    update_post_meta($id, '_rootedpsyche_brand_asset', $name);
    return $id;
}
try {
    $logo = rootedpsyche_import_brand_asset('/tmp/rootedpsyche-brand-logo.png', 'logo');
    $icon = rootedpsyche_import_brand_asset('/tmp/rootedpsyche-brand-icon.png', 'icon');
    update_option('rootedpsyche_logo_attachment_id', $logo);
    update_option('site_icon', $icon);
    echo "Branding installed: logo attachment $logo, site icon $icon.\n";
} catch (Throwable $e) { fwrite(STDERR, $e->getMessage() . "\n"); exit(1); }
