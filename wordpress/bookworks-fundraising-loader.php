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


/**
 * Campaign widgets are presentation owned by RootedOps, not BookWorks HTML.
 * Do not write them into post_content: this preserves the managed HTML checksum
 * and allows the BookWorks importer to continue detecting manual edits.
 *
 * Givebutter's official WordPress widget plugin must be installed and configured
 * for custom <givebutter-widget> elements to become interactive. The direct
 * campaign link remains usable if the plugin or scripts are unavailable.
 */
function rootedops_bookworks_fundraising_campaigns() {
    return [
        'rooted-psyche-fundraising:spiritual-center' => [
            'url' => 'https://givebutter.com/rooted-psyche-spiritual-center',
            'button' => 'gV17eG',
            'form' => 'pzeYw6',
            'goal' => 'paXben',
            'heading' => 'Support the Spiritual Center Fund',
        ],
    ];
}

function rootedops_bookworks_current_campaign() {
    if (!is_singular('page')) { return null; }
    $post = get_queried_object();
    if (!$post instanceof WP_Post) { return null; }
    // Never show a donation widget on a published page through this draft
    // integration until a separate release decision has been made.
    if ($post->post_status !== 'draft') { return null; }
    $key = get_post_meta($post->ID, '_bookworks_publication_key', true);
    $campaigns = rootedops_bookworks_fundraising_campaigns();
    return is_string($key) && isset($campaigns[$key]) ? $campaigns[$key] : null;
}

add_filter('the_content', function ($content) {
    if (!in_the_loop() || !is_main_query()) { return $content; }
    $campaign = rootedops_bookworks_current_campaign();
    if (!$campaign || strpos($content, 'bookworks-landing') === false) {
        return $content;
    }
    $url = esc_url($campaign['url']);
    $goal = esc_attr($campaign['goal']);
    $button = esc_attr($campaign['button']);
    $form = esc_attr($campaign['form']);
    $heading = esc_html($campaign['heading']);
    $top = '<aside class="bookworks-donation-top" aria-label="Fundraising progress and donation">'
        . '<givebutter-widget id="' . $goal . '"></givebutter-widget>'
        . '<givebutter-widget id="' . $button . '"></givebutter-widget>'
        . '<p class="bookworks-donation-fallback"><a href="' . $url . '" rel="noopener noreferrer">Donate to the Spiritual Center Fund</a></p>'
        . '</aside>';
    $bottom = '<section class="bookworks-donation-form" aria-label="Sanctuary donation form">'
        . '<h2>' . $heading . '</h2>'
        . '<givebutter-widget id="' . $form . '"></givebutter-widget>'
        . '<p class="bookworks-donation-fallback">You can also <a href="' . $url
        . '" rel="noopener noreferrer">donate securely on Givebutter</a>.</p>'
        . '</section>';
    return $top . $content . $bottom;
}, 20);


/*
 * The sanctuary image is presentation media, not part of BookWorks post_content.
 * An administrator associates an existing WordPress Media Library attachment with
 * draft page 15 using _rootedops_sanctuary_image_id. No remote image hotlinking.
 * WordPress validates the attachment ID before rendering it.
 */
add_filter('the_content', function ($content) {
    if (!in_the_loop() || !is_main_query()) { return $content; }
    $campaign = rootedops_bookworks_current_campaign();
    if (!$campaign) { return $content; }
    $post = get_queried_object();
    if (!$post instanceof WP_Post) { return $content; }
    $image_id = absint(get_post_meta($post->ID, '_rootedops_sanctuary_image_id', true));
    if (!$image_id || !wp_attachment_is_image($image_id)) { return $content; }
    $image = wp_get_attachment_image($image_id, 'large', false, [
        'class' => 'bookworks-sanctuary-photo',
        'loading' => 'eager',
        'fetchpriority' => 'high',
        'alt' => 'Rocky mountain valley with sparse regrowth and standing burned trees near the proposed Rooted Psyche sanctuary.',
    ]);
    if (!$image) { return $content; }
    $figure = '<figure class="bookworks-sanctuary-figure">' . $image
        . '<figcaption>Landscape surrounding the proposed Rooted Psyche sanctuary near Livermore, Colorado.</figcaption>'
        . '</figure>';
    // Run after the campaign widget filter: insert between its CTA and the
    // managed manuscript, without changing the stored manuscript itself.
    $needle = '<div class="bookworks-landing">';
    $position = strpos($content, $needle);
    if ($position === false) { return $content; }
    $position += strlen($needle);
    return substr($content, 0, $position) . $figure . substr($content, $position);
}, 30);
