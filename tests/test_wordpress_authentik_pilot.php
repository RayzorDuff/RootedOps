<?php
/** Standalone WordPress-hook stubs for the disabled-by-default OIDC pilot. */
declare(strict_types=1);
define('ABSPATH', __DIR__);
define('ROOTEDOPS_AUTHENTIK_WP_PILOT', true);
define('ROOTEDOPS_AUTHENTIK_WP_SITE', 'rootedpsyche');
define('ROOTEDOPS_AUTHENTIK_WP_MANAGED_IDS', [2]);
$GLOBALS['rootedops_hooks'] = [];
$GLOBALS['rootedops_users'] = [];
$GLOBALS['rootedops_meta'] = [];
function add_filter($name, $callback, $priority = 10, $args = 1) {
    $GLOBALS['rootedops_hooks'][$name][] = $callback;
}
function add_action($name, $callback, $priority = 10, $args = 1) {
    $GLOBALS['rootedops_hooks'][$name][] = $callback;
}
class WP_User {
    public $ID;
    public $roles;
    public $user_email;
    public function __construct(int $id, string $email, array $roles = []) {
        $this->ID = $id; $this->user_email = $email; $this->roles = $roles;
    }
    public function add_role($role) { if (!in_array($role, $this->roles, true)) $this->roles[] = $role; }
    public function remove_role($role) { $this->roles = array_values(array_diff($this->roles, [$role])); }
}
$GLOBALS['wpdb'] = new class { public function get_blog_prefix() { return 'wp_'; } };
function get_users($args) {
    $matches = [];
    foreach ($GLOBALS['rootedops_users'] as $u) {
        if (get_user_meta($u->ID, $args['meta_key'], true) === $args['meta_value']) $matches[] = $u;
    }
    return array_slice($matches, 0, $args['number']);
}
function get_user_by($field, $email) {
    foreach ($GLOBALS['rootedops_users'] as $u) {
        if ($field === 'email' && strcasecmp($u->user_email, $email) === 0) return $u;
    }
    return false;
}
function get_user_meta($id, $key, $single = true) {
    $value = $GLOBALS['rootedops_meta'][$id][$key] ?? '';
    return $single ? $value : ($value === '' ? [] : [$value]);
}
function get_user_option($key, $id) { return get_user_meta($id, 'wp_' . $key, true); }
function update_user_meta($id, $key, $value) {
    $GLOBALS['rootedops_meta'][$id][$key] = $value;
}
function assert_pilot($condition, string $message) {
    if (!$condition) { fwrite(STDERR, "FAIL: $message\n"); exit(1); }
}
require __DIR__ . '/../wordpress/mu-plugins/rootedops-wordpress-authentik.php';
assert_pilot(rootedops_oidc_pilot_enabled(), 'explicit test opt-in');
$person = new WP_User(2, 'example-person@rootedpsyche.org');
$GLOBALS['rootedops_users'][] = $person;
update_user_meta(2, 'wp_openid-connect-generic-subject-identity', 'stable-sub-001');
$valid = ['sub' => 'stable-sub-001', 'email' => 'example-person@rootedpsyche.org',
    'email_verified' => true, 'groups' => ['rootedpsyche-board-directors']];
$create = $GLOBALS['rootedops_hooks']['openid-connect-generic-user-creation-test'][0];
$sync = $GLOBALS['rootedops_hooks']['openid-connect-generic-update-user-using-current-claim'][0];
$gate = $GLOBALS['rootedops_hooks']['rootedpsyche_board_library_authorized'][0];
assert_pilot($create(true, $valid) === false, 'automatic creation denied during pilot');
assert_pilot(rootedops_oidc_linked_user($valid)->ID === 2, 'native plugin subject prelink resolves');
assert_pilot(rootedops_oidc_linked_user(array_merge($valid, ['sub' => 'different-person'])) === null, 'unlinked subject denied');
$sync($person, $valid);
assert_pilot(in_array('board_director', $person->roles, true), 'authentik board role projected');
assert_pilot($gate(true, $person) === true, 'fresh claim authorizes board');
update_user_meta(2, 'rootedops_board_claim_at', time() - 301);
assert_pilot($gate(true, $person) === false, 'expired claim denied');
$sync($person, array_merge($valid, ['groups' => ['rootedpsyche-spiritual-practitioners']]));
assert_pilot(!in_array('board_director', $person->roles, true), 'remove board when group removed');
assert_pilot($gate(true, $person) === false, 'non-board denied');
$admin = new WP_User(7, 'site-admin@example.invalid', ['administrator']);
$GLOBALS['rootedops_users'][] = $admin;
update_user_meta(7, 'wp_openid-connect-generic-subject-identity', 'admin-sub');
$sync($admin, ['sub' => 'admin-sub', 'email_verified' => true, 'groups' => ['rootedpsyche-board-directors']]);
assert_pilot(in_array('administrator', $admin->roles, true), 'administrator remains administrator');
assert_pilot($gate(true, $admin) === true, 'local admin recovery board access');
$legacy = new WP_User(4, 'legacy@example.invalid', ['board_director']);
assert_pilot($gate(true, $legacy) === true, 'unmigrated director retains access');
$sync($person, array_merge($valid, ['email' => 'wrong@example.invalid']));
assert_pilot(!in_array('board_director', $person->roles, true), 'canonical email mismatch denied');
update_user_meta(2, 'rootedops_approved_workspace_email', 'approved@rootedpsyche.org');
$sync($person, array_merge($valid, ['email' => 'approved@rootedpsyche.org']));
assert_pilot(in_array('board_director', $person->roles, true), 'approved separate organizational email accepted');
$sync($person, $valid);
assert_pilot(!in_array('board_director', $person->roles, true), 'old contact email is not approved authentication email');
$native = 'openid-connect-generic-subject-identity';
$global = new WP_User(8, 'global@example.invalid');
$GLOBALS['rootedops_users'][] = $global;
update_user_meta(8, $native, 'global-sub');
assert_pilot(rootedops_oidc_linked_user(['sub'=>'global-sub'])->ID === 8, 'global metadata resolves');
update_user_meta(8, 'wp_' . $native, 'global-sub');
assert_pilot(rootedops_oidc_linked_user(['sub'=>'global-sub'])->ID === 8, 'same account both formats resolves');
update_user_meta(8, 'wp_' . $native, 'conflict');
assert_pilot(rootedops_oidc_linked_user(['sub'=>'global-sub']) === null, 'conflicting formats rejected');
update_user_meta(8, $native, 'stable-sub-001');
assert_pilot(rootedops_oidc_linked_user($valid) === null, 'cross-account collision rejected');
$sync($person, $valid);
assert_pilot(get_user_meta(2, 'rootedops_board_claim_result', true) === 'subject_mismatch', 'collision reason recorded');
// Remove the intentional collision before testing session snapshots.
update_user_meta(8, $native, 'other-sub');
update_user_meta(2, 'rootedops_approved_workspace_email', 'approved@rootedpsyche.org');
$session_claim = array_merge($valid, ['email' => 'approved@rootedpsyche.org']);
$jwt = array_merge($session_claim, ['iat' => time(), 'exp' => time() + 300]);
$snapshot = rootedops_oidc_session_snapshot($person, $session_claim, $jwt, ['expires_in' => 300]);
assert_pilot($snapshot['authorized'] === true && $snapshot['until'] <= time()+300, 'fresh validated claims produce bounded session snapshot');
assert_pilot(!rootedops_oidc_session_snapshot($person, $session_claim, array_merge($jwt,['groups'=>[]]), ['expires_in'=>300])['authorized'], 'both claims must authorize');
assert_pilot(!rootedops_oidc_session_snapshot($person, $session_claim, array_merge($jwt,['sub'=>'other-sub']), ['expires_in'=>300])['authorized'], 'mismatched session subject denied');
assert_pilot(!rootedops_oidc_session_snapshot($person, $session_claim, array_merge($jwt,['exp'=>time()-1]), ['expires_in'=>300])['authorized'], 'expired signed claim denied');
assert_pilot(!rootedops_oidc_session_snapshot($person, $session_claim, $jwt, ['expires_in'=>0])['authorized'], 'missing valid access lifetime denied');
assert_pilot(!rootedops_oidc_session_renewal_enabled(), 'new session renewal remains explicitly opt-in');
echo "WordPress authentik pilot acceptance tests passed\n";
