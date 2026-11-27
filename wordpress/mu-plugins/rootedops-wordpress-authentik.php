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
    return get_user_meta($id, 'rootedops_board_managed', true) === '1' || (defined('ROOTEDOPS_AUTHENTIK_WP_MANAGED_IDS')
        && is_array(ROOTEDOPS_AUTHENTIK_WP_MANAGED_IDS)
        && in_array($id, ROOTEDOPS_AUTHENTIK_WP_MANAGED_IDS, true));
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
    if (rootedops_oidc_session_renewal_enabled()) {
        return rootedops_oidc_session_access($user_id);
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
        wp_die('Board access is unavailable. Please sign in again through RootedOps Identity or contact the board administrator.', 'Board access required', ['response' => 403]);
    }
}, 1);

/** Explicit second-stage opt-in; preserve the accepted pilot until deployed. */
function rootedops_oidc_session_renewal_enabled(): bool {
    return rootedops_oidc_pilot_enabled()
        && defined('ROOTEDOPS_AUTHENTIK_WP_SESSION_RENEWAL')
        && ROOTEDOPS_AUTHENTIK_WP_SESSION_RENEWAL === true;
}

function rootedops_oidc_session_claim_valid($user, $claim): bool {
    if (!$user instanceof WP_User || !is_array($claim)
        || !rootedops_oidc_managed_user((int) $user->ID)
        || array_intersect(['administrator', 'customer'], (array) $user->roles)) {
        return false;
    }
    $linked = rootedops_oidc_linked_user($claim);
    $approved = get_user_meta($user->ID, 'rootedops_approved_workspace_email', true);
    $expected = $approved ?: $user->user_email;
    return $linked && (int) $linked->ID === (int) $user->ID
        && is_string($expected) && str_ends_with(strtolower($expected), '@rootedpsyche.org')
        && ($claim['email_verified'] ?? false) === true
        && is_string($claim['email'] ?? null)
        && strcasecmp($claim['email'], $expected) === 0
        && rootedops_oidc_board_claim($claim);
}

function rootedops_oidc_session_snapshot($user, $claim, $id_claim, $response): array {
    $now = time();
    $expires = filter_var($response['expires_in'] ?? null, FILTER_VALIDATE_INT);
    $exp = filter_var($id_claim['exp'] ?? null, FILTER_VALIDATE_INT);
    $iat = filter_var($id_claim['iat'] ?? null, FILTER_VALIDATE_INT);
    $sub = rootedops_oidc_subject($claim);
    $valid = $expires > 0 && $exp > $now && $iat >= $now - 300 && $iat <= $now + 30
        && $sub !== '' && $sub === rootedops_oidc_subject($id_claim)
        && rootedops_oidc_session_claim_valid($user, $claim)
        && rootedops_oidc_session_claim_valid($user, $id_claim);
    return ['subject' => $sub, 'authorized' => (bool) $valid,
        'checked_at' => $now, 'until' => $valid ? min($now + 300, $now + $expires, $exp) : $now];
}

// Capture the exact login response in this request, never read user-wide token
// metadata to authenticate a different browser session.
add_filter('openid-connect-generic-remember-me', static function ($remember, $user, $response, $id_claim, $claim, $subject) {
    if (rootedops_oidc_session_renewal_enabled() && $user instanceof WP_User
        && rootedops_oidc_managed_user((int) $user->ID)) {
        $GLOBALS['rootedops_oidc_pending_session'] = [
            'id' => (int) $user->ID,
            'snapshot' => rootedops_oidc_session_snapshot($user, $claim, $id_claim, $response),
            'refresh' => is_string($response['refresh_token'] ?? null) ? $response['refresh_token'] : '',
        ];
    }
    return $remember;
}, 20, 6);

add_action('set_logged_in_cookie', static function ($cookie, $expire, $expiration, $id, $scheme, $token): void {
    $pending = $GLOBALS['rootedops_oidc_pending_session'] ?? null;
    if (!rootedops_oidc_session_renewal_enabled() || !$pending || $pending['id'] !== (int) $id) {
        return;
    }
    unset($GLOBALS['rootedops_oidc_pending_session']);
    $manager = WP_Session_Tokens::get_instance($id);
    $session = $manager->get($token);
    if (!is_array($session)) {
        return;
    }
    $session['rootedops_board_authorization'] = $pending['snapshot'];
    $session['openid-connect-generic-refresh'] = ['refresh_token' => $pending['refresh']];
    $manager->update($token, $session);
}, 20, 6);

// Use a request-local copy of upstream settings. Disable the competing native
// user-wide refresh only for managed users; no persisted option is changed.
add_filter('openid-connect-generic-settings', static function ($settings) {
    if (!rootedops_oidc_session_renewal_enabled()) {
        return $settings;
    }
    $GLOBALS['rootedops_oidc_settings'] = clone $settings;
    if (is_user_logged_in() && rootedops_oidc_managed_user((int) get_current_user_id())) {
        $settings = clone $settings;
        $settings->token_refresh_enable = false;
    }
    return $settings;
}, PHP_INT_MAX);

function rootedops_oidc_session_access(int $id): bool {
    if ($id < 1 || $id !== (int) get_current_user_id()) {
        return false;
    }
    $token = wp_get_session_token();
    if (!$token) {
        return false;
    }
    $session = WP_Session_Tokens::get_instance($id)->get($token);
    $snapshot = $session['rootedops_board_authorization'] ?? [];
    $now = time();
    return ($snapshot['authorized'] ?? false) === true
        && !empty($snapshot['subject'])
        && (int) (rootedops_oidc_linked_user(['sub' => $snapshot['subject']])->ID ?? 0) === $id
        && ($snapshot['checked_at'] ?? 0) <= $now
        && ($snapshot['until'] ?? 0) > $now
        && $snapshot['until'] <= $snapshot['checked_at'] + 300;
}

/** Use upstream cryptographic validation, not decoded or cached token claims. */
function rootedops_oidc_refresh_claims(string $refresh): ?array {
    $s = $GLOBALS['rootedops_oidc_settings'] ?? null;
    if (!$s || !$s->client_id || !$s->client_secret
        || $s->endpoint_token !== 'https://auth.danks.store/application/o/token/'
        || $s->endpoint_userinfo !== 'https://auth.danks.store/application/o/userinfo/'
        || $s->endpoint_jwks !== 'https://auth.danks.store/application/o/rootedpsyche-wordpress/jwks/'
        || $s->issuer !== 'https://auth.danks.store/application/o/rootedpsyche-wordpress/'
        || $s->no_sslverify || $s->allow_internal_idp) {
        return null;
    }
    $logger = new OpenID_Connect_Generic_Option_Logger('error', false, 0);
    $client = new OpenID_Connect_Generic_Client($s->client_id, $s->client_secret, $s->scope,
        $s->endpoint_login, $s->endpoint_userinfo, $s->endpoint_token, '', $s->acr_values,
        $s->endpoint_jwks, $s->issuer, $s->jwks_cache_ttl, 180, false, $logger);
    $result = $client->request_new_tokens($refresh);
    if (is_wp_error($result)) {
        return null;
    }
    $response = $client->get_token_response($result);
    if (!is_array($response) || empty($response['access_token'])) {
        return null;
    }
    $id_claim = $client->get_id_token_claim($response);
    if (!is_array($id_claim) || $client->validate_id_token_claim($id_claim) !== true) {
        return null;
    }
    $claim = $client->get_user_claim($response);
    if (!is_array($claim) || $client->validate_user_claim($claim, $id_claim) !== true) {
        return null;
    }
    return [$claim, $id_claim, $response];
}

// Refresh before any board page or file gate. Serialize refreshes for a user,
// because WordPress stores all that user's session records in one meta value.
add_action('init', static function (): void {
    if (!rootedops_oidc_session_renewal_enabled() || !is_user_logged_in()) {
        return;
    }
    $user = wp_get_current_user();
    $id = (int) $user->ID;
    if (!rootedops_oidc_managed_user($id) || array_intersect(['administrator', 'customer'], (array) $user->roles)
        || rootedops_oidc_session_access($id)) {
        return;
    }
    $token = wp_get_session_token();
    if (!$token) {
        return;
    }
    global $wpdb;
    $lock = 'rootedops-board-' . hash('sha256', $wpdb->prefix . ':' . $id);
    $lock = substr($lock, 0, 64);
    if ((string) $wpdb->get_var($wpdb->prepare('SELECT GET_LOCK(%s, 5)', $lock)) !== '1') {
        return;
    }
    try {
        // Discard any request-local cached copy before reading current sessions.
        wp_cache_delete($id, 'user_meta');
        $manager = WP_Session_Tokens::get_instance($id);
        $session = $manager->get($token);
        if (!is_array($session) || rootedops_oidc_session_access($id)) {
            return;
        }
        $snapshot = $session['rootedops_board_authorization'] ?? null;
        $refresh = $session['openid-connect-generic-refresh']['refresh_token'] ?? '';
        // Older sessions and ordinary password logins must authenticate anew.
        if (!is_array($snapshot) || empty($snapshot['subject']) || !is_string($refresh) || $refresh === '') {
            return;
        }
        if (($snapshot['checked_at'] ?? 0) > time() - 15) {
            return; // Bound retries after a denied or unavailable response.
        }
        $renewed = rootedops_oidc_refresh_claims($refresh);
        $next = ['subject' => $snapshot['subject'], 'authorized' => false, 'checked_at' => time(), 'until' => time()];
        if ($renewed) {
            [$claim, $id_claim, $response] = $renewed;
            if (rootedops_oidc_subject($claim) === $snapshot['subject']) {
                $next = rootedops_oidc_session_snapshot($user, $claim, $id_claim, $response);
                if (is_string($response['refresh_token'] ?? null) && $response['refresh_token'] !== '') {
                    $session['openid-connect-generic-refresh']['refresh_token'] = $response['refresh_token'];
                }
                // Project only current validated claims; no cached token can renew access.
                do_action('openid-connect-generic-update-user-using-current-claim', $user, $claim);
                if (!$next['authorized']) {
                    $user->remove_role('board_director');
                }
            }
        }
        $session['rootedops_board_authorization'] = $next;
        $manager->update($token, $session);
        if (!$next['authorized']) {
            $user->remove_role('board_director');
            update_user_meta($id, 'rootedops_board_claim_authorized', '0');
            update_user_meta($id, 'rootedops_board_claim_result', 'session_renewal_denied');
        }
    } finally {
        $wpdb->get_var($wpdb->prepare('SELECT RELEASE_LOCK(%s)', $lock));
    }
}, 20);
