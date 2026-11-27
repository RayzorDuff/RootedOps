<?php
/**
 * RootedOps WordPress OIDC subject prelink (CLI-only, dry-run by default).
 * NEVER run with inferred emails. Supply a validated issuer-specific OIDC sub
 * for the human's authentik identity and the approved existing WordPress ID.
 * Uses the native OpenID Connect Generic subject identity metadata; never infer
 * a subject from email or numeric authentik user ID.
 *
 * ROOTEDOPS_WP_USER_ID=2 ROOTEDOPS_OIDC_SUB='<verified-id-token-sub>' php this-file.php
 * ROOTEDOPS_WP_USER_ID=2 ROOTEDOPS_OIDC_SUB='<verified-id-token-sub>' ROOTEDOPS_APPLY=YES php this-file.php
 */
if (PHP_SAPI !== 'cli') {
    http_response_code(403);
    exit;
}
$wp_root = getenv('ROOTEDOPS_WP_ROOT') ?: '/var/www/html';
$bootstrap = rtrim($wp_root, '/') . '/wp-load.php';
if (!is_file($bootstrap)) {
    fwrite(STDERR, "WordPress bootstrap is unavailable\n");
    exit(2);
}
require_once $bootstrap;
$id = filter_var(getenv('ROOTEDOPS_WP_USER_ID'), FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
$sub = getenv('ROOTEDOPS_OIDC_SUB');
$apply = getenv('ROOTEDOPS_APPLY') === 'YES';
if (!$id || !is_string($sub) || $sub === '' || strlen($sub) > 255
    || trim($sub) !== $sub || preg_match('/[\x00-\x1F\x7F]/', $sub)) {
    fwrite(STDERR, "Provide an existing WordPress user ID and an exact validated OIDC subject via private environment\n");
    exit(2);
}
$expected_host = 'rootedpsyche.org';
$host = (string) (wp_parse_url(site_url(), PHP_URL_HOST) ?: '');
if ($host !== $expected_host) {
    fwrite(STDERR, "Refusing: intended Rooted Psyche WordPress site not found\n");
    exit(2);
}
$user = get_userdata($id);
if (!$user instanceof WP_User || in_array('administrator', (array) $user->roles, true)
    || in_array('customer', (array) $user->roles, true)) {
    fwrite(STDERR, "Refusing: WordPress ID unavailable or is an excluded account type\n");
    exit(2);
}
$key = 'openid-connect-generic-subject-identity';
foreach (array_unique([$key, $wpdb->get_blog_prefix() . $key]) as $meta_key) {
    foreach (get_users(['meta_key' => $meta_key, 'meta_value' => $sub,
        'number' => 2, 'count_total' => false]) as $match) {
        if ((int) $match->ID !== $id) {
            fwrite(STDERR, "Refusing: subject linked to another account\n"); exit(3);
        }
    }
    foreach (get_user_meta($id, $meta_key, false) as $stored) {
        if ($stored !== '' && $stored !== $sub) {
            fwrite(STDERR, "Refusing: conflicting subject metadata\n"); exit(3);
        }
    }
}
$existing = get_user_option($key, $id);
$approved = getenv('ROOTEDOPS_APPROVED_WORKSPACE_EMAIL');
if ($approved !== false && (!is_email($approved) || !str_ends_with(strtolower($approved), '@rootedpsyche.org'))) {
    fwrite(STDERR, "Invalid approved Workspace email\n"); exit(2);
}
$prior = get_user_meta($id, 'rootedops_approved_workspace_email', true);
if ($prior !== '' && $approved !== false && strcasecmp($prior, $approved) !== 0) {
    fwrite(STDERR, "Existing approved email differs; reconcile separately\n"); exit(3);
}
if (!$apply) {
    echo "DRY RUN: target WP ID validated; no subject metadata changed. Set ROOTEDOPS_APPLY=YES after operator approval.\n";
    exit(0);
}
if ($approved !== false) {
    update_user_meta($id, 'rootedops_approved_workspace_email', strtolower($approved));
}
if ($existing === $sub) {
    echo "No change: exact subject already linked to approved WordPress ID.\n";
    exit(0);
}
if (!update_user_option($id, 'openid-connect-generic-subject-identity', $sub, false)) {
    fwrite(STDERR, "Subject metadata was not saved\n");
    exit(4);
}
echo "Linked validated OIDC subject to existing WordPress user ID; no roles changed.\n";
