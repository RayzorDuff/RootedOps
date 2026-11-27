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
    $users = get_users([
        'meta_key' => '_rootedops_authentik_subject',
        'meta_value' => $sub,
        'number' => 2,
        'count_total' => false,
    ]);
    return count($users) === 1 && $users[0] instanceof WP_User ? $users[0] : null;
}

// Pilot must never create a WP user; this also avoids modifying WooCommerce customers.
add_filter('openid-connect-generic-user-creation-test', static function ($allow) {
    return rootedops_oidc_pilot_enabled() ? false : $allow;
}, 1);

// This hook is called only after the OIDC client has validated its token/userinfo.
add_filter('openid-connect-generic-user-login-test', static function ($allow, $claim) {
    if (!rootedops_oidc_pilot_enabled() || !$allow) {
        return $allow;
    }
    $user = rootedops_oidc_linked_user($claim);
    if (!$user || in_array('administrator', (array) $user->roles, true)
        || in_array('customer', (array) $user->roles, true)) {
        return false;
    }
    // The generic client can also select WP users using email during its
    // existing-user lookup. Refuse this pilot unless that lookup unambiguously
    // resolves to the exact, preapproved WP ID. A different account email is
    // a migration/reconciliation task, NOT an automatic account merge.
    $email = isset($claim['email']) && is_string($claim['email'])
        ? strtolower(trim($claim['email'])) : '';
    $found = $email !== '' ? get_user_by('email', $email) : false;
    if (!($found instanceof WP_User) || $found->ID !== $user->ID
        || !isset($claim['email_verified']) || $claim['email_verified'] !== true) {
        return false;
    }
    // Board role can be removed on next login; never reject an approved user
    // solely because their board assignment was removed.
    return true;
}, 1, 2);

// Project group membership only when the authenticated subject matches this WP
// user's explicitly provisioned subject. Never promote WP administrators.
add_action('openid-connect-generic-update-user-using-current-claim',
    static function ($user, $claim): void {
        if (!rootedops_oidc_pilot_enabled() || !($user instanceof WP_User)) {
            return;
        }
        $linked = rootedops_oidc_linked_user($claim);
        if (!$linked || $linked->ID !== $user->ID
            || in_array('administrator', (array) $user->roles, true)
            || in_array('customer', (array) $user->roles, true)) {
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
    return $user instanceof WP_User && rootedops_oidc_board_access((int) $user->ID);
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
        || !rootedops_oidc_board_access((int) $user->ID)) {
        nocache_headers();
        status_header(403);
        exit;
    }
}, 1);
