<?php
/** CLI-only, redacted OIDC claim acceptance report. No tokens or personal identifiers. */
if (PHP_SAPI !== 'cli') { http_response_code(403); exit; }
require '/var/www/html/wp-load.php';
$id = filter_var(getenv('ROOTEDOPS_WP_USER_ID'), FILTER_VALIDATE_INT, ['options'=>['min_range'=>1]]);
if (!$id || wp_parse_url(site_url(), PHP_URL_HOST) !== 'rootedpsyche.org') exit(2);
$user = get_userdata($id);
if (!$user) exit(2);
$sub = get_user_option('openid-connect-generic-subject-identity', $id);
$report = ['wp_id'=>$id, 'roles'=>$user->roles, 'persistent_subject'=>is_string($sub) && $sub !== ''];
foreach (['last-user-claim','last-id-token-claim'] as $key) {
    $claim = get_user_option('openid-connect-generic-'.$key, $id);
    $report[$key] = [
        'present'=>is_array($claim),
        'subject_matches'=>is_array($claim) && is_string($sub) && $sub !== '' && ($claim['sub'] ?? null) === $sub,
        'verified_email'=>is_array($claim) && ($claim['email_verified'] ?? null) === true,
        'email_matches_wp'=>is_array($claim) && is_string($claim['email'] ?? null) && strcasecmp($claim['email'], $user->user_email) === 0,
        'groups_array'=>is_array($claim) && is_array($claim['groups'] ?? null),
        'board_group'=>is_array($claim) && is_array($claim['groups'] ?? null) && in_array('rootedpsyche-board-directors', $claim['groups'], true),
    ];
}
echo wp_json_encode($report, JSON_PRETTY_PRINT) . PHP_EOL;
