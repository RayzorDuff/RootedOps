<?php
/**
 * Associate an existing Media Library photo with the managed Spiritual Center
 * draft. CLI only. Does not edit post_content, publish, or modify BookWorks hash.
 *
 * Usage (inside WordPress container):
 *   php /tmp/set_sanctuary_image.php <attachment-id>
 */
if (PHP_SAPI !== 'cli') { exit(1); }
require '/var/www/html/wp-load.php';
if (($argc !== 2 && $argc !== 3) || !ctype_digit($argv[1]) || (int)$argv[1] < 1 || ($argc === 3 && $argv[2] !== 'concept')) {
    fwrite(STDERR, "Usage: php set_sanctuary_image.php <attachment-id> [concept]\n");
    exit(2);
}
$id = (int)$argv[1];
if (!wp_attachment_is_image($id)) {
    fwrite(STDERR, "Attachment is not a WordPress image\n");
    exit(1);
}
$matches = get_posts([
    'post_type' => 'page',
    'post_status' => 'draft',
    'numberposts' => -1,
    'meta_key' => '_bookworks_publication_key',
    'meta_value' => 'rooted-psyche-fundraising:spiritual-center',
]);
if (count($matches) !== 1 || (int)$matches[0]->ID !== 15) {
    fwrite(STDERR, "Expected exactly one managed draft at page 15; refusing change\n");
    exit(1);
}
$meta_key = $argc === 3 ? '_rootedops_sanctuary_concept_image_id' : '_rootedops_sanctuary_image_id';
update_post_meta(15, $meta_key, $id);
echo "Linked attachment $id ($meta_key) to managed draft page 15; publication status unchanged.\n";
