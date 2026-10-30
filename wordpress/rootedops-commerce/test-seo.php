<?php
// Synthetic WordPress API boundary harness, no WordPress installation required.
define('ABSPATH', __DIR__);
$on_product = true; $metadata = []; $hooks = [];
function is_product() { global $on_product; return $on_product; }
function get_queried_object_id() { return 42; }
function get_post_meta($id, $key, $single) { global $metadata; return $metadata[$key] ?? ''; }
function wp_strip_all_tags($text) { return strip_tags($text); }
function esc_attr($text) { return htmlspecialchars($text, ENT_QUOTES, 'UTF-8'); }
function add_filter($key, $callback, $priority) { global $hooks; $hooks[$key] = $callback; }
function add_action($key, $callback, $priority) { add_filter($key, $callback, $priority); }
function check($condition) { if (!$condition) { throw new Exception('SEO contract failure'); } }
require __DIR__ . '/rootedops-commerce.php';
check(rootedops_commerce_seo_title('Fallback') === 'Fallback');
$metadata = ['_rootedops_seo_title'=>'<b>ERP title</b>', '_rootedops_seo_description'=>'ERP "description" & more'];
check(rootedops_commerce_seo_title('Fallback') === 'ERP title');
check(rootedops_commerce_seo_description('Fallback') === 'ERP "description" & more');
ob_start(); rootedops_commerce_seo_head(); $head = ob_get_clean();
check(str_contains($head, '&quot;description&quot; &amp; more'));
$on_product = false; check(rootedops_commerce_seo_title('Fallback') === 'Fallback');
$on_product = true; define('WPSEO_VERSION', 'synthetic');
ob_start(); rootedops_commerce_seo_head(); check(ob_get_clean() === '');
check(isset($hooks['wpseo_title']) && isset($hooks['wpseo_metadesc']));
echo "SEO core/Yoast boundary checks passed\n";
