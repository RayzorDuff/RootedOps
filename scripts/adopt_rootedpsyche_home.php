<?php
/**
 * Explicit, guarded adoption of the existing Grav-derived WordPress front page.
 * CLI only. plan: read-only; apply: write only BookWorks management metadata.
 * Never modify post_content, title, slug, status, menus or page_on_front.
 */
if (PHP_SAPI !== 'cli') exit(1);
require '/var/www/html/wp-load.php';
function adoption_fail($message) { fwrite(STDERR, $message . "\n"); exit(1); }
if ($argc !== 4 || !in_array($argv[1], ['plan', 'apply'], true)) {
    adoption_fail('Usage: php adopt_rootedpsyche_home.php plan|apply EXPECTED_PAGE_ID EXPECTED_CONTENT_SHA256');
}
$mode=$argv[1];
$id=filter_var($argv[2], FILTER_VALIDATE_INT);
$expected=$argv[3];
if (!$id || !preg_match('/^[a-f0-9]{64}$/', $expected)) adoption_fail('Invalid expected page ID or SHA256');
if (get_option('show_on_front') !== 'page' || (int)get_option('page_on_front') !== (int)$id)
    adoption_fail('Static front-page configuration differs from expected ID');
$page=get_post($id);
if (!$page || $page->post_type !== 'page' || $page->post_status !== 'publish' ||
    $page->post_name !== 'home' || $page->post_title !== 'Home')
    adoption_fail('Existing homepage identity or publication state differs from inventory');
$actual=hash('sha256', $page->post_content);
if (!hash_equals($expected, $actual)) adoption_fail('Homepage content changed since inventory; refusing adoption');
if (get_post_meta($id, '_rootedpsyche_grav_imported', true) !== '1')
    adoption_fail('Missing Grav import provenance');
if (!is_file(WP_CONTENT_DIR.'/mu-plugins/rootedpsyche-givebutter.php'))
    adoption_fail('Givebutter front-page plugin unavailable');
$qr=get_posts(['post_type'=>'attachment','post_status'=>'inherit','posts_per_page'=>-1,
    'meta_key'=>'_rootedpsyche_grav_qr','meta_value'=>'1']);
if (count($qr)!==1 || !wp_attachment_is_image((int)$qr[0]->ID))
    adoption_fail('Expected exactly one valid imported QR attachment');
$key='rooted-psyche-website:homepage';
$managed=get_posts(['post_type'=>'page','post_status'=>'any','numberposts'=>-1,
    'meta_key'=>'_bookworks_publication_key','meta_value'=>$key]);
if (count($managed)>1 || (count($managed)===1 && (int)$managed[0]->ID !== (int)$id))
    adoption_fail('BookWorks homepage key already belongs to another page');
$stored_key=get_post_meta($id,'_bookworks_publication_key',true);
$stored_sha=get_post_meta($id,'_bookworks_managed_html_sha256',true);
if ($stored_key !== '' && $stored_key !== $key) adoption_fail('Page already managed under another publication');
if ($stored_sha !== '' && !hash_equals($stored_sha,$actual))
    adoption_fail('Existing managed checksum does not match content');
$history=get_post_meta($id,'_bookworks_native_release_history',true);
if ($history !== '' && !is_array($history)) adoption_fail('Unrecognized release history');
if (!is_array($history)) $history=[];
$already=($stored_key===$key && $stored_sha===$actual);
if ($stored_key === $key && !$already) adoption_fail('Incomplete prior adoption; inspect manually');
echo wp_json_encode(['mode'=>$mode,'action'=>$already?'already-adopted':'adopt-existing-front-page',
    'page_id'=>$id,'slug'=>$page->post_name,'status'=>$page->post_status,
    'content_sha256'=>$actual,'qr_attachment_id'=>(int)$qr[0]->ID,
    'givebutter_plugin_present'=>true,'release_snapshot_exists'=>isset($history[$actual])],
    JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES)."\n";
if ($mode==='plan' || $already) exit(0);
$history[$actual]=['content'=>$page->post_content,'title'=>$page->post_title,
    'status'=>$page->post_status,'source_commit'=>'grav-import'];
if (!update_post_meta($id,'_bookworks_native_release_history',$history))
    adoption_fail('Failed to persist original homepage snapshot; adoption not started');
if (!update_post_meta($id,'_bookworks_managed_html_sha256',$actual))
    adoption_fail('Could not set managed checksum; inspect partial adoption');
if (!update_post_meta($id,'_bookworks_publication_key',$key))
    adoption_fail('Could not bind BookWorks publication key; inspect partial adoption');
update_post_meta($id,'_bookworks_native_active_sha256',$actual);
update_post_meta($id,'_bookworks_source_commit','grav-import');
$after=get_post($id);
if (!$after || hash('sha256',$after->post_content)!==$actual ||
    (int)get_option('page_on_front')!==(int)$id || $after->post_status!=='publish')
    adoption_fail('Post-adoption verification failed');
echo "Adopted existing front page metadata; content untouched, historical rollback snapshot stored.\n";
