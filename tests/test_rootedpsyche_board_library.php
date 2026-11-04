<?php
/**
 * Isolated CLI security checks for the file resolver; run with php.
 * Doesn't need WordPress or access to production Google Drive.
 */
declare(strict_types=1);
$root = sys_get_temp_dir() . '/rp-board-' . bin2hex(random_bytes(8));
mkdir($root . '/2026-10-01', 0700, true);
mkdir($root . '/2026-11-10', 0700, true);
file_put_contents($root . '/2026-10-01/Minutes.pdf', 'safe file');
file_put_contents($root . '/2026-10-01/script.php', 'not allowed');
file_put_contents($root . '/private.pdf', 'outside the date folder');
symlink($root . '/private.pdf', $root . '/2026-10-01/symlink.pdf');
mkdir($root . '/2026-10-01/nested');
file_put_contents($root . '/2026-10-01/nested/hidden.pdf', 'nested');
define('ABSPATH', $root);
define('RP_BOARD_LIBRARY_ROOT', $root);
function add_action(...$args): void {}
function add_shortcode(...$args): void {}
function wp_json_encode($value): string { return json_encode($value, JSON_THROW_ON_ERROR); }
require __DIR__ . '/../wordpress/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php';

function expect(bool $condition, string $message): void {
    if (!$condition) {
        throw new RuntimeException('Failed: ' . $message);
    }
}
try {
    expect(rp_board_library_dates() === ['2026-11-10', '2026-10-01'], 'date folders sorted');
    expect(rp_board_library_file('2026-10-01', 'Minutes.pdf') !== null, 'valid PDF found');
    expect(rp_board_library_file('2026-10-01', 'script.php') === null, 'PHP not downloadable');
    expect(rp_board_library_file('2026-10-01', 'symlink.pdf') === null, 'symlink blocked');
    expect(rp_board_library_file('2026-10-01', '../private.pdf') === null, 'traversal blocked');
    expect(rp_board_library_file('2026-10-01', 'nested/hidden.pdf') === null, 'nested blocked');
    expect(rp_board_library_file('2026-10-32', 'Minutes.pdf') === null, 'invalid day blocked');
    expect(rp_board_library_file('2026-09-01', 'Minutes.pdf') === null, 'missing date blocked');
    expect(rp_board_library_decode_file('@@@@') === null, 'invalid token blocked');
    expect(rp_board_library_decode_file(rp_board_library_encode_file('2026-10-01','Minutes.pdf'))
        === ['2026-10-01','Minutes.pdf'], 'token roundtrip');
    echo "Board document resolver checks passed\n";
} finally {
    unlink($root . '/2026-10-01/symlink.pdf');
    unlink($root . '/2026-10-01/Minutes.pdf');
    unlink($root . '/2026-10-01/script.php');
    unlink($root . '/2026-10-01/nested/hidden.pdf');
    rmdir($root . '/2026-10-01/nested');
    rmdir($root . '/2026-10-01');
    rmdir($root . '/2026-11-10');
    unlink($root . '/private.pdf');
    rmdir($root);
}
