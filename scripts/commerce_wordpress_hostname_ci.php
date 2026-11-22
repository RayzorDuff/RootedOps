<?php
if (getenv('COMMERCE_NATIVE_WOO_FIXTURE') !== '1') throw new RuntimeException('Disposable Woo required');
$mode = $args[0];
$old = 'https://shop-test.danks.store';
$new = 'https://dankmushrooms.net';
function domain_expect($ok, $reason) { if (!$ok) throw new RuntimeException($reason); }
if ($mode === 'seed') {
    $content = '<!-- wp:paragraph --><p><a href="' . $old . '/my-account/">account</a> ' . $old . '.evil.invalid</p><!-- /wp:paragraph -->';
    $serialized = serialize(array($old => array('url' => $old . '/product/synthetic/')));
    $page = wp_insert_post(wp_slash(array('post_type'=>'page', 'post_status'=>'publish', 'post_title'=>'Hostname fixture', 'post_content'=>$content)));
    $block = wp_insert_post(wp_slash(array('post_type'=>'wp_block', 'post_status'=>'publish', 'post_content'=>$serialized)));
    $legacy = wp_insert_post(array('post_type'=>'shop_order','post_status'=>'wc-pending','post_content'=>$old));
    update_post_meta($page, 'synthetic_identity', $old);
    update_option('rootedops_hostname_ci', compact('page','block','legacy','content','serialized','old'));
} else {
    $data = get_option('rootedops_hostname_ci');
    $after = $mode === 'after';
    $content = $after ? str_replace($old . '/my-account/', $new . '/my-account/', $data['content']) : $data['content'];
    domain_expect(get_post($data['page'])->post_content === $content, 'HTML/Gutenberg exact host replacement');
    $serialized = $after ? serialize(array($old => array('url'=>$new . '/product/synthetic/'))) : $data['serialized'];
    domain_expect(get_post($data['block'])->post_content === $serialized, 'Serialization or identity key drift');
    domain_expect(get_post($data['legacy'])->post_content === $old, 'Historical order modified');
    domain_expect(get_post_meta($data['page'], 'synthetic_identity', true) === $old, 'Metadata modified');
    domain_expect($data['old'] === $old, 'Options modified');
    echo 'Native hostname ' . $mode . " checks passed\n";
}
