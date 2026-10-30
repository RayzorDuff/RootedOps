<?php
/**
 * Plugin Name: RootedOps Commerce SEO
 * Description: Render ERP-owned WooCommerce SEO metadata with core or Yoast.
 * Version: 0.1.0
 */
if (!defined('ABSPATH')) { exit; }

function rootedops_commerce_seo_value($key) {
    if (!function_exists('is_product') || !is_product()) { return ''; }
    $value = get_post_meta(get_queried_object_id(), $key, true);
    return is_string($value) ? trim(wp_strip_all_tags($value)) : '';
}
function rootedops_commerce_seo_title($title) {
    $value = rootedops_commerce_seo_value('_rootedops_seo_title');
    return $value !== '' ? $value : $title;
}
function rootedops_commerce_seo_description($description) {
    $value = rootedops_commerce_seo_value('_rootedops_seo_description');
    return $value !== '' ? $value : $description;
}
function rootedops_commerce_seo_head() {
    if (defined('WPSEO_VERSION')) { return; } // Yoast owns the head presenter.
    $description = rootedops_commerce_seo_value('_rootedops_seo_description');
    if ($description !== '') {
        echo '<meta name="description" content="' . esc_attr($description) . '" />' . "\n";
    }
}
add_filter('pre_get_document_title', 'rootedops_commerce_seo_title', 20);
add_filter('wpseo_title', 'rootedops_commerce_seo_title', 20);
add_filter('wpseo_metadesc', 'rootedops_commerce_seo_description', 20);
add_action('wp_head', 'rootedops_commerce_seo_head', 1);
