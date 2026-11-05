<?php
/** Rooted Psyche Board Readiness: guarded, CLI-only update of the EXISTING protected page. */
if (PHP_SAPI !== 'cli') exit(1);
require '/var/www/html/wp-load.php';
function rp_bwp_fail(string $why): void { fwrite(STDERR, $why . "\n"); exit(1); }
if ($argc !== 4 || !in_array($argv[2], ['check','stage','promote','rollback'], true))
    rp_bwp_fail('Usage: php board_protected_publish.php payload.json check|stage|promote|rollback SHA-or-dash');
$mode = $argv[2];
$rollback_sha = $argv[3];
$payload = json_decode(file_get_contents($argv[1]), true);
if (!is_array($payload) || ($payload['schema_version'] ?? null) !== 1
    || ($payload['publication_id'] ?? null) !== 'rooted-psyche-corporate-record-book'
    || ($payload['profile'] ?? null) !== 'board-readiness'
    || ($payload['slug'] ?? null) !== 'board-readiness'
    || ($payload['layout'] ?? null) !== 'fundraising-landing'
    || ($payload['media'] ?? null) !== []
    || !preg_match('/^[a-f0-9]{40}$/D', $payload['source_commit'] ?? '')
    || !is_string($payload['html'] ?? null)
    || !hash_equals(hash('sha256', $payload['html']), $payload['html_sha256'] ?? '')
    || trim(wp_strip_all_tags($payload['html'])) === '')
    rp_bwp_fail('Unsupported or invalid restricted BookWorks package');

if (!function_exists('members_get_post_roles') || !get_role('board_director'))
    rp_bwp_fail('Members role gate is unavailable; refusing publication');
$parent = get_page_by_path('board', OBJECT, 'page');
$page = get_page_by_path('board/board-readiness', OBJECT, 'page');
if (!$parent || !$page || $page->post_parent !== (int)$parent->ID
    || $parent->post_name !== 'board' || $page->post_name !== 'board-readiness'
    || $page->post_status !== 'publish' || $parent->post_status !== 'publish'
    || (int)$page->ID === (int)$parent->ID)
    rp_bwp_fail('Board page hierarchy, identity or status changed');

function rp_bwp_roles($id): array {
    $roles = members_get_post_roles($id);
    if (!is_array($roles)) rp_bwp_fail('Invalid Members roles');
    $roles = array_values(array_unique($roles));
    sort($roles);
    return $roles;
}
$allowed = ['administrator', 'board_director'];
$parent_roles = rp_bwp_roles($parent->ID);
$child_roles = rp_bwp_roles($page->ID);
foreach ([$parent_roles, $child_roles] as $roles) {
    if (array_diff($roles, $allowed))
        rp_bwp_fail('Unexpected role can view Board material');
}
if (!in_array('board_director', $parent_roles, true))
    rp_bwp_fail('Board Portal parent must explicitly restrict to board_director');
if ($child_roles && !in_array('board_director', $child_roles, true))
    rp_bwp_fail('Board Readiness child restriction must include board_director');
// Parent protection is inherited by unconfigured children in Members.
if (!function_exists('members_can_current_user_view_post'))
    rp_bwp_fail('Members access API is missing');
if (!isset($payload['title']) || !is_string($payload['title'])) rp_bwp_fail('Invalid publication title');

$next_html = wp_kses_post($payload['html']);
if (trim(wp_strip_all_tags($next_html)) === '') rp_bwp_fail('Empty sanitized Board publication');
$history = get_post_meta($page->ID, '_bookworks_board_release_history', true);
if (!is_array($history)) $history = [];
$current_hash = hash('sha256', $page->post_content);
$managed_hash = get_post_meta($page->ID, '_bookworks_board_managed_sha256', true);
if (is_string($managed_hash) && $managed_hash !== ''
    && !hash_equals($managed_hash, $current_hash))
    rp_bwp_fail('Manual Board Readiness page edits detected; refusing overwrite');
$expected_hash = hash('sha256', $next_html);
if ($mode === 'rollback') {
    if (!preg_match('/^[a-f0-9]{64}$/D', $rollback_sha) || !isset($history[$rollback_sha]))
        rp_bwp_fail('Rollback snapshot is not available');
    $target = $history[$rollback_sha];
    if (!is_array($target) || !isset($target['content'], $target['source_commit'])
        || !hash_equals(hash('sha256', $target['content']), $rollback_sha))
        rp_bwp_fail('Rollback snapshot is invalid');
    $next_html = $target['content'];
    $expected_hash = $rollback_sha;
} elseif ($rollback_sha !== '-') {
    rp_bwp_fail('Unexpected rollback argument');
}
echo wp_json_encode([
    'mode' => $mode,
    'page_id' => (int)$page->ID,
    'parent_id' => (int)$parent->ID,
    'parent_roles' => $parent_roles,
    'child_roles' => $child_roles,
    'current_sha256' => $current_hash,
    'expected_sha256' => $expected_hash,
    'source_commit' => $payload['source_commit'],
    'rollback_snapshots' => array_keys($history),
], JSON_PRETTY_PRINT) . "\n";
if ($mode === 'check' || $mode === 'stage') {
    echo 'Preflight complete; no WordPress write performed.\n';
    exit(0);
}
if (hash_equals($current_hash, $expected_hash)) {
    echo "Already matches expected content; no mutation.\n";
    exit(0);
}
if (!isset($history[$current_hash])) {
    $history[$current_hash] = [
        'content' => $page->post_content,
        'source_commit' => get_post_meta($page->ID, '_bookworks_board_source_commit', true),
    ];
}
if (update_post_meta($page->ID, '_bookworks_board_release_history', $history) === false
    && get_post_meta($page->ID, '_bookworks_board_release_history', true) !== $history)
    rp_bwp_fail('Unable to persist rollback snapshot');
$result = wp_update_post(['ID' => (int)$page->ID, 'post_content' => wp_slash($next_html)], true);
if (is_wp_error($result) || (int)$result !== (int)$page->ID)
    rp_bwp_fail('Page content update failed');
$after = get_post($page->ID);
if (!$after || $after->post_status !== 'publish'
    || $after->post_parent !== (int)$parent->ID || $after->post_name !== 'board-readiness'
    || rp_bwp_roles($parent->ID) !== $parent_roles || rp_bwp_roles($page->ID) !== $child_roles
    || !hash_equals(hash('sha256', $after->post_content), $expected_hash))
    rp_bwp_fail('Post-write protection or checksum mismatch: investigate and restore before continuing');
update_post_meta($page->ID, '_bookworks_board_managed_sha256', $expected_hash);
update_post_meta($page->ID, '_bookworks_board_source_commit',
    $mode === 'rollback' ? $target['source_commit'] : $payload['source_commit']);
echo "Protected Board Readiness content updated; permissions and hierarchy unchanged.\n";
