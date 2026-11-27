<?php
/** Standalone WordPress-hook stubs for the disabled-by-default OIDC pilot. */
declare(strict_types=1);
define('ABSPATH', __DIR__);
define('ROOTEDOPS_AUTHENTIK_WP_PILOT', true);
define('ROOTEDOPS_AUTHENTIK_WP_SITE', 'rootedpsyche');
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
    return $GLOBALS['rootedops_meta'][$id][$key] ?? '';
}
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
update_user_meta(2, 'rootedops_authentik_subject', 'stable-sub-001');
$valid = ['sub' => 'stable-sub-001', 'email' => 'example-person@rootedpsyche.org',
    'email_verified' => true, 'groups' => ['rootedpsyche-board-directors']];
$login = $GLOBALS['rootedops_hooks']['openid-connect-generic-user-login-test'][0];
$create = $GLOBALS['rootedops_hooks']['openid-connect-generic-user-creation-test'][0];
$sync = $GLOBALS['rootedops_hooks']['openid-connect-generic-update-user-using-current-claim'][0];
$gate = $GLOBALS['rootedops_hooks']['rootedpsyche_board_library_authorized'][0];
assert_pilot($create(true) === false, 'no new WP users');
assert_pilot($login(true, $valid) === true, 'prelinked verified login');
assert_pilot($login(true, array_merge($valid, ['email_verified' => false])) === false, 'unverified denied');
assert_pilot($login(true, array_merge($valid, ['sub' => 'different-person'])) === false, 'unlinked denied');
assert_pilot($login(true, array_merge($valid, ['email' => 'other@rootedpsyche.org'])) === false, 'email mismatch denied');
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
update_user_meta(7, 'rootedops_authentik_subject', 'admin-sub');
assert_pilot($login(true, ['sub' => 'admin-sub', 'email' => 'site-admin@example.invalid',
    'email_verified' => true]) === false, 'administrator cannot use pilot');
assert_pilot($gate(true, $admin) === true, 'local admin recovery board access');
echo "WordPress authentik pilot acceptance tests passed\n";
