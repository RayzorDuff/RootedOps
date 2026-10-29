<?php
/**
 * Plugin Name: Rooted Psyche Givebutter Embed
 * Description: Loads the existing Givebutter widget script on the homepage.
 */
add_action('wp_enqueue_scripts', function () {
    if (is_front_page()) {
        wp_enqueue_script(
            'rootedpsyche-givebutter',
            'https://widgets.givebutter.com/latest.umd.cjs?acct=AuYLMcoSt1X5PvLu&p=other',
            [],
            null,
            true
        );
    }
});

/**
 * Render the custom element after the static homepage content.
 * WordPress sanitization strips unknown tags from imported post_content.
 */
add_filter('the_content', function ($content) {
    if (!is_admin() && is_main_query() && in_the_loop() && is_front_page()) {
        $content .= "\n" . '<div class="rootedpsyche-donation-widget"><givebutter-widget id="gJeP4L"></givebutter-widget></div>';
    }
    return $content;
}, 20);
