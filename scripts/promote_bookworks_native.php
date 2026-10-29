<?php
/** Guarded WordPress-native BookWorks promotion and content-addressed rollback. CLI only. */
if (PHP_SAPI !== 'cli') exit(1);
require '/var/www/html/wp-load.php';
function bw_native_fail($m) { fwrite(STDERR, $m . "\n"); exit(1); }
if ($argc !== 4 || !in_array($argv[2], ['check','promote','rollback'], true)) bw_native_fail('Usage: php promote_bookworks_native.php payload.json check|promote|rollback HASH-or-dash');
$p = json_decode(file_get_contents($argv[1]), true);
if (!is_array($p) || ($p['schema_version'] ?? null) !== 1 || ($p['layout'] ?? null) !== 'fundraising-landing') bw_native_fail('Invalid native fundraising payload');
foreach (['publication_id','profile','slug','source_commit','html','html_sha256'] as $f) if (!isset($p[$f]) || !is_string($p[$f])) bw_native_fail('Missing field '.$f);
$key = $p['publication_id'].':'.$p['profile'];

if (!preg_match('/^[a-z0-9-]+:[a-z0-9-]+$/',$key) || !preg_match('/^[a-z0-9-]+$/',$p['slug']) || !preg_match('/^[a-f0-9]{40}$/',$p['source_commit']) || !preg_match('/^[a-f0-9]{64}$/',$p['html_sha256']) || !hash_equals($p['html_sha256'],hash('sha256',$p['html']))) bw_native_fail('Payload integrity failure');
$pages = get_posts(['post_type'=>'page','post_status'=>'any','numberposts'=>-1,'meta_key'=>'_bookworks_publication_key','meta_value'=>$key]);
if (count($pages)!==1) bw_native_fail('Expected exactly one managed page');
$page=$pages[0]; $id=(int)$page->ID;
if ($page->post_name!==$p['slug'] || !in_array($page->post_status,['draft','publish'],true)) bw_native_fail('Page identity/status mismatch');
// Resolve the single typed QR marker using the existing WordPress attachment.
// Do not accept arbitrary HTML or remote media from the BookWorks payload.
$approved_html = $p['html'];
if ($key === 'rooted-psyche-website:homepage') {
    if ($id !== 5 || (int)get_option('page_on_front') !== $id ||
        get_option('show_on_front') !== 'page' || $page->post_name !== 'home' ||
        get_post_meta($id, '_rootedpsyche_grav_imported', true) !== '1')
        bw_native_fail('Front-page identity or Grav provenance changed');
    if (!is_file(WP_CONTENT_DIR . '/mu-plugins/rootedpsyche-givebutter.php'))
        bw_native_fail('Existing Givebutter front-page integration missing');
    $marker='<p>BOOKWORKS_ROOTEDPSYCHE_QR</p>';
    if (substr_count($approved_html, $marker) !== 1)
        bw_native_fail('Exactly one homepage QR marker required');
    $qr=get_posts(['post_type'=>'attachment','post_status'=>'inherit',
        'posts_per_page'=>-1,'meta_key'=>'_rootedpsyche_grav_qr','meta_value'=>'1']);
    if (count($qr)!==1 || (int)$qr[0]->ID!==8 || !wp_attachment_is_image(8))
        bw_native_fail('Imported homepage QR attachment changed');
    $url=wp_get_attachment_url(8);
    if (!$url) bw_native_fail('Imported QR attachment URL unavailable');
    $qr_html='<figure class="wp-block-image"><a href="https://givebutter.com/2yTHnU" target="_blank" rel="noopener noreferrer"><img src="'.esc_url($url).'" alt="Rooted Psyche donation QR code" class="wp-image-8"/></a></figure>';
    $approved_html=str_replace($marker,$qr_html,$approved_html);
}
$approved_html=wp_kses_post($approved_html);
$managed=get_post_meta($id,'_bookworks_managed_html_sha256',true);
$actual=hash('sha256',$page->post_content);
if (!is_string($managed) || !hash_equals($managed,$actual)) bw_native_fail('Manual content edit or missing managed checksum');
$mode=$argv[2]; $target=$argv[3];
$history=get_post_meta($id,'_bookworks_native_release_history',true);
if (!is_array($history)) $history=[];
if ($mode==='promote' || $mode==='check') {
    if ($target!=='-') bw_native_fail('Unexpected rollback hash');
    if ($page->post_status==='draft' && get_post_meta($id,'_bookworks_source_commit',true)!==$p['source_commit']) bw_native_fail('Staged source revision differs from approved release');
    $expected=hash('sha256',$approved_html);
    if ($page->post_status==='draft' && !hash_equals($expected,$actual)) bw_native_fail('Draft differs from approved native payload');
    if ($page->post_status==='publish' && $mode==='promote') {
        // Published website revisions are explicit approved-release promotions,
        // not draft staging; retain the WordPress page ID and live URL.
        if (!in_array($p['profile'], ['privacy-policy','terms-of-service','reserve-office-time','homepage'], true)
            || ($p['media'] ?? []) !== []) bw_native_fail('Published revision must be an approved text-only website profile');
        if (hash_equals($expected,$actual)) {
            echo "Published page already matches approved release; no content change required.\n";
            if ($mode==='promote') exit(0);
        }
    }
    if ($page->post_status==='publish' && $mode==='promote' && $p['publication_id'] !== 'rooted-psyche-website') bw_native_fail('Published updates are supported only for reviewed text-only website releases');
} else {
    if (!preg_match('/^[a-f0-9]{64}$/',$target) || !isset($history[$target])) bw_native_fail('Unknown rollback snapshot');
    if ($page->post_status!=='publish') bw_native_fail('Rollback only permitted on published managed page');
    $snapshot=$history[$target];
    if (!is_array($snapshot) || !isset($snapshot['content'],$snapshot['status'],$snapshot['source_commit'],$snapshot['title']) || hash('sha256',$snapshot['content'])!==$target) bw_native_fail('Corrupt rollback snapshot');
    if (!in_array($snapshot['status'],['draft','publish'],true)) bw_native_fail('Unsupported snapshot status');
}
echo wp_json_encode(['action'=>$mode,'page_id'=>$id,'status'=>$page->post_status,'current_sha256'=>$actual,'history_hashes'=>array_keys($history),'target'=>$target],JSON_PRETTY_PRINT)."\n";
if ($mode==='check') exit(0);
$before=['content'=>$page->post_content,'title'=>$page->post_title,'status'=>$page->post_status,'source_commit'=>get_post_meta($id,'_bookworks_source_commit',true)];
if (!isset($history[$actual])) $history[$actual]=$before;
if ($mode==='rollback') {
    $next=$snapshot;
    $new_status=$snapshot['status'];
} else {
    $next=$before;
    $new_status='publish';
}
if (!update_post_meta($id,'_bookworks_native_release_history',$history)) {
    $saved=get_post_meta($id,'_bookworks_native_release_history',true);
    if ($saved!==$history) bw_native_fail('Unable to persist release history; refusing mutation');
}
$update=['ID'=>$id,'post_status'=>$new_status];
if ($mode==='rollback') {
    $update['post_content']=wp_slash($next['content']);
    $update['post_title']=$next['title'];
} elseif ($page->post_status==='publish') {
    // The existing published page is updated atomically without unpublishing.
    // The earlier content has been persisted as a content-hashed snapshot.
    $update['post_content']=wp_slash($approved_html);
    // Preserve the adopted front-page title and URL as imported from Grav.
    if ($key !== 'rooted-psyche-website:homepage') $update['post_title']=$p['title'];
}
$result=wp_update_post($update,true);
if (is_wp_error($result) || (int)$result!==$id) bw_native_fail('WordPress update failed; history retained');
$after=get_post($id);
if (!$after || $after->post_status!==$new_status || $after->post_name!==$p['slug']) bw_native_fail('Post-update identity/status verification failed');
if ($mode==='rollback') {
    if (hash('sha256',$after->post_content)!==$target) bw_native_fail('Rollback content mismatch');
    update_post_meta($id,'_bookworks_source_commit',$next['source_commit']);
} elseif ($mode==='promote') {
    $expected_after=hash('sha256',$approved_html);
    if (!hash_equals($expected_after,hash('sha256',$after->post_content))) bw_native_fail('Promoted content differs from approved payload');
    update_post_meta($id,'_bookworks_source_commit',$p['source_commit']);
}
update_post_meta($id,'_bookworks_managed_html_sha256',hash('sha256',$after->post_content));
update_post_meta($id,'_bookworks_native_active_sha256',hash('sha256',$after->post_content));
echo "Native ".$mode." completed for page ".$id."; status=".$after->post_status." sha256=".hash('sha256',$after->post_content)."\n";
