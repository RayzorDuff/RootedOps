<?php
/**
 * RootedOps site-specific WordPress presentation for BookWorks landing pages.
 * Installed as an MU plugin; no theme edits and no public-page publishing.
 */
if (!defined('ABSPATH')) { exit; }

add_action('wp_enqueue_scripts', function () {
    if (!is_singular('page')) { return; }
    $post = get_queried_object();
    if (!$post instanceof WP_Post) { return; }
    $key = get_post_meta($post->ID, '_bookworks_publication_key', true);
    if (!is_string($key) || strpos($key, 'rooted-psyche-fundraising:') !== 0) { return; }
    $css_path = WP_CONTENT_DIR . '/mu-plugins/bookworks-fundraising.css';
    if (!is_file($css_path)) { return; }
    wp_enqueue_style(
        'bookworks-fundraising',
        content_url('mu-plugins/bookworks-fundraising.css'),
        [],
        (string) filemtime($css_path)
    );
});

/* Apply landing-page chrome changes only to BookWorks-managed fundraising pages. */
add_filter('body_class', function ($classes) {
    if (!is_singular('page')) { return $classes; }
    $post = get_queried_object();
    if (!$post instanceof WP_Post) { return $classes; }
    $key = get_post_meta($post->ID, '_bookworks_publication_key', true);
    if (is_string($key) && strpos($key, 'rooted-psyche-fundraising:') === 0) {
        $classes[] = 'bookworks-fundraising-page';
    }
    return $classes;
});
