<?php
/** Standalone hierarchy resolver checks: no WordPress installation necessary. */
declare(strict_types=1);
$root = sys_get_temp_dir() . '/rp-hierarchy-' . bin2hex(random_bytes(8));
mkdir($root . '/Governance Documents/Colorado', 0700, true);
mkdir($root . '/Governance Documents/IRS', 0700, true);
mkdir($root . '/Board Resolutions/2026', 0700, true);
file_put_contents($root . '/Governance Documents/Colorado/Articles.pdf', 'articles');
file_put_contents($root . '/Governance Documents/IRS/Letter.pdf', 'letter');
file_put_contents($root . '/Board Resolutions/2026/Adopted.pdf', 'adopted');
file_put_contents($root . '/outside.pdf', 'private');
symlink($root . '/outside.pdf', $root . '/Governance Documents/Colorado/link.pdf');
define('ABSPATH', $root);
define('RP_BOARD_SUPPLEMENTS_ROOT', $root);
function add_action(...$a): void {}
function add_shortcode(...$a): void {}
function wp_json_encode($v): string { return json_encode($v, JSON_THROW_ON_ERROR); }
require __DIR__ . '/../wordpress/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php';

function verify_h(bool $value, string $message): void {
    if (!$value) throw new RuntimeException($message);
}
try {
    verify_h(rp_board_hierarchy_resolve('governance','Colorado/Articles.pdf') !== null, 'Colorado record');
    verify_h(rp_board_hierarchy_resolve('governance','IRS/Letter.pdf') !== null, 'IRS record');
    verify_h(rp_board_hierarchy_resolve('resolutions','2026/Adopted.pdf') !== null, 'Board resolution');
    verify_h(rp_board_hierarchy_resolve('governance','2026/Adopted.pdf') === null, 'Cross-library isolation');
    verify_h(rp_board_hierarchy_resolve('resolutions','Colorado/Articles.pdf') === null, 'Reverse isolation');
    verify_h(rp_board_hierarchy_resolve('governance','../outside.pdf') === null, 'Traversal');
    verify_h(rp_board_hierarchy_resolve('governance','Colorado/link.pdf') === null, 'Symlink');
    verify_h(rp_board_hierarchy_resolve('governance','Colorado/../../outside.pdf') === null, 'Nested traversal');
    verify_h(rp_board_hierarchy_resolve('governance','Colorado/Articles.php') === null, 'Unsupported extension');
    $token = rp_board_hierarchy_encode('governance','Colorado/Articles.pdf');
    verify_h(rp_board_hierarchy_decode($token) === ['governance','Colorado/Articles.pdf'], 'Token roundtrip');
    verify_h(rp_board_hierarchy_decode('@@@') === null, 'Invalid token');
    echo "Board hierarchy resolver checks passed\n";
} finally {
    unlink($root . '/Governance Documents/Colorado/link.pdf');
    unlink($root . '/Governance Documents/Colorado/Articles.pdf');
    unlink($root . '/Governance Documents/IRS/Letter.pdf');
    unlink($root . '/Board Resolutions/2026/Adopted.pdf');
    unlink($root . '/outside.pdf');
    rmdir($root . '/Governance Documents/Colorado');
    rmdir($root . '/Governance Documents/IRS');
    rmdir($root . '/Governance Documents');
    rmdir($root . '/Board Resolutions/2026');
    rmdir($root . '/Board Resolutions');
    rmdir($root);
}
