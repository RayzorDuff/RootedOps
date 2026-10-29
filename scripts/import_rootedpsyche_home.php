<?php
// Run only inside the trusted WordPress container via CLI.
if (PHP_SAPI !== 'cli') { exit(1); }
require '/var/www/html/wp-load.php';
$source = file_get_contents('/tmp/rootedpsyche-grav-home.md');
if ($source === false) { fwrite(STDERR, "Missing source markdown\n"); exit(1); }
$source = preg_replace('/\A---\R.*?\R---\R/s', '', $source, 1);
$lines = preg_split('/\R/', $source);
$html = '';
$widget = false;
foreach ($lines as $line) {
    $line = trim($line);
    if ($line === '') continue;
    if (preg_match('/^## (.+)$/u', $line, $m)) {
        $html .= '<!-- wp:heading --><h2 class="wp-block-heading">' . esc_html($m[1]) . '</h2><!-- /wp:heading -->' . "\n";
    } elseif (preg_match('/^### (.+)$/u', $line, $m)) {
        $html .= '<!-- wp:heading {"level":3} --><h3 class="wp-block-heading">' . esc_html($m[1]) . '</h3><!-- /wp:heading -->' . "\n";
    } elseif (preg_match('/^!\[QR\]\(qr\.png\)$/', $line)) {
        // The imported media attachment is inserted below.
        $html .= '%%ROOTEDPSYCHE_QR%%' . "\n";
    } elseif (strpos($line, '<givebutter-widget') === 0) {
        $widget = true;
    } else {
        $html .= '<!-- wp:paragraph --><p>' . esc_html($line) . '</p><!-- /wp:paragraph -->' . "\n";
    }
}
$qr = '/tmp/rootedpsyche-qr.png';
if (!is_file($qr)) { fwrite(STDERR, "Missing QR source image\n"); exit(1); }
$existing_media = get_posts(['post_type'=>'attachment','post_status'=>'inherit','meta_key'=>'_rootedpsyche_grav_qr','meta_value'=>'1','posts_per_page'=>1]);
if ($existing_media) {
    $attachment_id = $existing_media[0]->ID;
} else {
    $upload = wp_upload_bits('rootedpsyche-grav-qr.png', null, file_get_contents($qr));
    if (!empty($upload['error'])) { fwrite(STDERR, $upload['error']."\n"); exit(1); }
    $attachment_id = wp_insert_attachment(['post_mime_type'=>'image/png','post_title'=>'Rooted Psyche QR','post_status'=>'inherit'], $upload['file']);
    if (is_wp_error($attachment_id)) { fwrite(STDERR, $attachment_id->get_error_message()."\n"); exit(1); }
    require_once ABSPATH.'wp-admin/includes/image.php';
    wp_update_attachment_metadata($attachment_id, wp_generate_attachment_metadata($attachment_id, $upload['file']));
    update_post_meta($attachment_id, '_rootedpsyche_grav_qr', '1');
}
$qr_url = wp_get_attachment_url($attachment_id);
$donation_url = getenv('ROOTEDPSYCHE_GIVEBUTTER_URL') ?: 'https://givebutter.com/2yTHnU';
if ($donation_url && !preg_match('~^https://([a-z0-9-]+\\.)*givebutter\\.com/~i', $donation_url)) {
    fwrite(STDERR, "Donation URL must be an HTTPS givebutter.com link.\\n"); exit(1);
}
$qr_html = '<!-- wp:image {"id":'.(int)$attachment_id.',"sizeSlug":"full"} --><figure class="wp-block-image size-full"><img src="'.esc_url($qr_url).'" alt="Rooted Psyche QR code" class="wp-image-'.(int)$attachment_id.'"/></figure><!-- /wp:image -->';
if ($donation_url) {
    $qr_html = str_replace('<img ', '<a href="'.esc_url($donation_url).'" target="_blank" rel="noopener noreferrer"><img ', $qr_html);
    $qr_html = str_replace('</figure>', '</a></figure>', $qr_html);
}
$html = str_replace('%%ROOTEDPSYCHE_QR%%', $qr_html, $html);
if ($widget) {
    $html .= '<!-- wp:html -->'."\n".
        '<givebutter-widget id="gJeP4L"></givebutter-widget>'."\n".
        '<!-- /wp:html -->'."\n";
}
$html .= '<!-- wp:heading --><h2 class="wp-block-heading">Donate to Rooted Psyche</h2><!-- /wp:heading -->'."\n";
$html .= '<!-- wp:paragraph --><p><a href="'.esc_url($donation_url).'" target="_blank" rel="noopener noreferrer">Donate to Rooted Psyche through Givebutter</a></p><!-- /wp:paragraph -->'."\n";
$html .= '<!-- wp:heading --><h2 class="wp-block-heading">Subscribe</h2><!-- /wp:heading -->'."\n";
$html .= '<!-- wp:paragraph --><p><a href="https://listmonk.rootedpsyche.org/subscription/form">Subscribe to the Rooted Psyche mailing list</a></p><!-- /wp:paragraph -->'."\n";
$html .= '<!-- wp:heading --><h2 class="wp-block-heading">Contact</h2><!-- /wp:heading -->'."\n";
$html .= '<!-- wp:paragraph --><p>For general questions, please contact us by email or phone.</p><!-- /wp:paragraph -->'."\n";
$html .= '<!-- wp:paragraph --><p><strong>Email:</strong> rootedpsyche [at] gmail [dot] com</p><!-- /wp:paragraph -->'."\n";
$html .= '<!-- wp:paragraph --><p><strong>Phone:</strong> nine seven zero · four zero eight · zero eight five eight</p><!-- /wp:paragraph -->'."\n";
$page_id = (int)get_option('page_on_front');
if (!$page_id || get_post_type($page_id) !== 'page') {
    fwrite(STDERR, "No valid static homepage configured. Configure Settings > Reading first.\n"); exit(1);
}
$page = get_post($page_id);
if (get_post_meta($page_id, '_rootedpsyche_grav_imported', true) !== '1' && trim($page->post_content) !== '') {
    fwrite(STDERR, "Homepage has content and was not previously imported; refusing to overwrite.\n"); exit(1);
}
$result = wp_update_post(['ID'=>$page_id,'post_content'=>wp_slash($html)], true);
if (is_wp_error($result)) { fwrite(STDERR, $result->get_error_message()."\n"); exit(1); }
update_post_meta($page_id, '_rootedpsyche_grav_imported', '1');
// Remove only the untouched WordPress sample page, never arbitrary content.
$sample = get_page_by_path('sample-page');
if ($sample && $sample->post_title === 'Sample Page' && (int)$sample->ID !== $page_id) {
    wp_trash_post($sample->ID);
    echo "Moved default Sample Page to trash.\\n";
}
echo "Updated existing static homepage ID $page_id; QR attachment ID $attachment_id. Review Givebutter rendering before cutover.\\n";
