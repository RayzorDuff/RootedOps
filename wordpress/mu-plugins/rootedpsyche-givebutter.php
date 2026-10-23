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
