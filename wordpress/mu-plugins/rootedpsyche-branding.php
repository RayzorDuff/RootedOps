<?php
/**
 * Plugin Name: Rooted Psyche Branding
 * Description: Replace the block-theme site title with the organization's logo.
 */
add_filter('render_block_core/site-title', function ($html, $block) {
    $id = (int) get_option('rootedpsyche_logo_attachment_id');
    if (!$id) return $html;
    $url = wp_get_attachment_url($id);
    if (!$url) return $html;
    return '<a class="rootedpsyche-brand" href="' . esc_url(home_url('/')) . '" aria-label="Rooted Psyche home"><img src="' . esc_url($url) . '" alt="Rooted Psyche" /></a>';
}, 10, 2);
add_action('wp_head', function () {
    echo '<style>.rootedpsyche-brand{display:inline-flex;align-items:center;max-width:170px}.rootedpsyche-brand img{display:block;width:100%;height:auto;max-height:105px;object-fit:contain}</style>' . "\n";
});
