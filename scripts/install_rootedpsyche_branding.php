<?php
if (PHP_SAPI !== 'cli') { exit(1); }
require '/var/www/html/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/image.php';
function rootedpsyche_import_brand_asset($file, $name) {
    if (!is_file($file)) { throw new RuntimeException("Missing asset: $file"); }
    $prior = get_posts(['post_type'=>'attachment','post_status'=>'inherit','meta_key'=>'_rootedpsyche_brand_asset','meta_value'=>$name,'posts_per_page'=>1]);
    if ($prior) { return (int)$prior[0]->ID; }
    $upload = wp_upload_bits($name . '.png', null, file_get_contents($file));
    if (!empty($upload['error'])) { throw new RuntimeException($upload['error']); }
    $id = wp_insert_attachment(['post_mime_type'=>'image/png','post_title'=>'Rooted Psyche ' . $name,'post_status'=>'inherit'], $upload['file']);
    if (is_wp_error($id)) { throw new RuntimeException($id->get_error_message()); }
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
