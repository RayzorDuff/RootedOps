<?php
/**
 * Plugin Name: RootedOps WordPress Authentik Bridge (pilot)
 * Description: Opt-in role projection for the OpenID Connect Generic Client. Never handles WooCommerce customers.
 * Version: 0.1.0
 * License: GPL-2.0-or-later
 */
defined('ABSPATH') || exit;

/**
 * Explicitly disabled until an administrator has reconciled the WordPress user
 * and authentik subject. Never enable globally in a shared WordPress image.
 */
function rootedops_oidc_pilot_enabled(): bool {
    return defined('ROOTEDOPS_AUTHENTIK_WP_PILOT')
        && ROOTEDOPS_AUTHENTIK_WP_PILOT === true
        && defined('ROOTEDOPS_AUTHENTIK_WP_SITE')
        && ROOTEDOPS_AUTHENTIK_WP_SITE === 'rootedpsyche';
}

// Explicit pilot cohort; legacy directors remain unchanged until reconciled.
function rootedops_oidc_managed_user(int $id): bool {
    return defined('ROOTEDOPS_AUTHENTIK_WP_MANAGED_IDS')
        && is_array(ROOTEDOPS_AUTHENTIK_WP_MANAGED_IDS)
        && in_array($id, ROOTEDOPS_AUTHENTIK_WP_MANAGED_IDS, true);
}

function rootedops_oidc_subject($claim): string {
    return is_array($claim) && isset($claim['sub']) && is_string($claim['sub'])
        ? trim($claim['sub']) : '';
}

function rootedops_oidc_board_claim($claim): bool {
    if (!is_array($claim) || !isset($claim['groups']) || !is_array($claim['groups'])) {
        return false;
    }
    return in_array('rootedpsyche-board-directors', $claim['groups'], true);
}

/**
 * Only admit explicitly pre-linked subjects. A mutable email address is never
 * used for privileged linking, even when Google reports it as verified.
 */
function rootedops_oidc_linked_user($claim): ?WP_User {
    $sub = rootedops_oidc_subject($claim);
    if ($sub === '' || strlen($sub) > 255) {
        return null;
    }
    $key = 'openid-connect-generic-subject-identity';
    $matches = [];
    foreach (array_unique([$key, $GLOBALS['wpdb']->get_blog_prefix() . $key]) as $meta_key) {
        foreach (get_users(['meta_key' => $meta_key, 'meta_value' => $sub,
            'number' => 2, 'count_total' => false]) as $candidate) {
            if (!$candidate instanceof WP_User) {
                return null;
            }
            $matches[(int) $candidate->ID] = $candidate;
        }
    }
    if (count($matches) !== 1) {
        return null;
    }
    $user = reset($matches);
    foreach (array_unique([$key, $GLOBALS['wpdb']->get_blog_prefix() . $key]) as $meta_key) {
        foreach ((array) get_user_meta($user->ID, $meta_key, false) as $stored) {
            if ($stored !== '' && $stored !== $sub) {
                return null;
            }
        }
    }
    return $user;
}

// This hook is the upstream client's actual conditional-creation filter.
add_filter('openid-connect-generic-user-creation-test', static function ($allow, $claim) {
    if (!rootedops_oidc_pilot_enabled()) {
        return $allow;
    }
    // Auto provisioning is deferred until a tested role lifecycle exists.
    return false;
}, 1, 2);

// Project group membership only when the authenticated subject matches this WP
// user's explicitly provisioned subject. Never promote WP administrators.
add_action('openid-connect-generic-update-user-using-current-claim',
    static function ($user, $claim): void {
        if (!rootedops_oidc_pilot_enabled() || !($user instanceof WP_User)) {
            return;
        }
        $linked = rootedops_oidc_linked_user($claim);
        if (!rootedops_oidc_managed_user((int) $user->ID)
            || in_array('administrator', (array) $user->roles, true)
            || in_array('customer', (array) $user->roles, true)) {
            return;
        }
        if (!$linked || (int) $linked->ID !== (int) $user->ID) {
            update_user_meta($user->ID, 'rootedops_board_claim_authorized', '0');
            update_user_meta($user->ID, 'rootedops_board_claim_at', time());
            update_user_meta($user->ID, 'rootedops_board_claim_result', 'subject_mismatch');
            $user->remove_role('board_director');
            return;
        }
        // A signed/validated Google/authentik claim must explicitly certify
        // the *canonical* email before any privileged role is projected.
        $approved = get_user_meta($user->ID, 'rootedops_approved_workspace_email', true);
        $expected_email = is_string($approved) && $approved !== '' ? $approved : $user->user_email;
        if (($claim['email_verified'] ?? false) !== true
            || !is_string($claim['email'] ?? null)
            || strcasecmp($claim['email'], $expected_email) !== 0) {
            $user->remove_role('board_director');
            update_user_meta($user->ID, 'rootedops_board_claim_authorized', '0');
            update_user_meta($user->ID, 'rootedops_board_claim_at', time());
            update_user_meta($user->ID, 'rootedops_board_claim_result', 'email_mismatch_or_unverified');
            return;
        }
        $board = rootedops_oidc_board_claim($claim);
        if ($board) {
            $user->add_role('board_director');
        } else {
            $user->remove_role('board_director');
        }
        // Snapshot is intentionally short-lived; stale board privileges fail
        // closed even if the WP browser session remains active.
        update_user_meta($user->ID, 'rootedops_board_claim_authorized', $board ? '1' : '0');
        update_user_meta($user->ID, 'rootedops_board_claim_result', $board ? 'authorized' : 'group_missing');
        update_user_meta($user->ID, 'rootedops_board_claim_at', time());
    }, 20, 2);

/**
 * Enforce board authorization on every protected page or file request when
 * explicitly enabled. The legacy board plugin is amended to call this filter.
 * A 5-minute authorization TTL bounds stale access, and will require renewal
 * of the OIDC session (or re-login) after expiry.
 */
function rootedops_oidc_board_access(int $user_id): bool {
    if (!rootedops_oidc_pilot_enabled()) {
        return true; // No behavior change until cutover.
    }
    if ($user_id < 1 || get_user_meta($user_id, 'rootedops_board_claim_authorized', true) !== '1') {
        return false;
    }
    $at = (int) get_user_meta($user_id, 'rootedops_board_claim_at', true);
    return $at > 0 && $at <= time() && time() - $at <= 300;
}

add_filter('rootedpsyche_board_library_authorized', static function ($authorized, $user) {
    if (!$authorized || !rootedops_oidc_pilot_enabled()) {
        return $authorized;
    }
    if ($user instanceof WP_User && in_array('administrator', (array) $user->roles, true)) {
        return true; // Independently recoverable local WP admin.
    }
    return $user instanceof WP_User && (!rootedops_oidc_managed_user((int) $user->ID)
        || rootedops_oidc_board_access((int) $user->ID));
}, 10, 2);

// Board page including descendants: no direct access on stale WordPress roles.
add_action('template_redirect', static function (): void {
    if (!rootedops_oidc_pilot_enabled() || !is_page()) {
        return;
    }
    $page = get_queried_object();
    if (!$page instanceof WP_Post) {
        return;
    }
    $cursor = $page;
    $board = false;
    for ($i = 0; $i < 12 && $cursor instanceof WP_Post; $i++) {
        if ($cursor->post_name === 'board' && (int) $cursor->post_parent === 0) {
            $board = true;
            break;
        }
        if (!$cursor->post_parent) {
            break;
        }
        $cursor = get_post($cursor->post_parent);
    }
    if (!$board || !is_user_logged_in()) {
        return; // WordPress/Members retain their anonymous login rules.
    }
    $user = wp_get_current_user();
    if (in_array('administrator', (array) $user->roles, true)) {
        return;
    }
    if (!in_array('board_director', (array) $user->roles, true)
        || (rootedops_oidc_managed_user((int) $user->ID)
            && !rootedops_oidc_board_access((int) $user->ID))) {
        nocache_headers();
        status_header(403);
        exit;
    }
}, 1);
