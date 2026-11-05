<?php
/** Standalone security tests for the two static board sections and BookWorks manifest. */
declare(strict_types=1);
$root = sys_get_temp_dir() . '/rp-sections-' . bin2hex(random_bytes(8));
mkdir($root . '/Governance Documents', 0700, true);
mkdir($root . '/Treasury Reports', 0700, true);
file_put_contents($root . '/Governance Documents/Bylaws.pdf', 'example');
file_put_contents($root . '/Treasury Reports/2026-Q4.xlsx', 'example');
file_put_contents($root . '/outside.pdf', 'not approved');
symlink($root . '/outside.pdf', $root . '/Governance Documents/shortcut.pdf');
define('ABSPATH', $root);
define('RP_BOARD_SUPPLEMENTS_ROOT', $root);
function add_action(...$args): void {}
function add_shortcode(...$args): void {}
function wp_json_encode($value): string { return json_encode($value, JSON_THROW_ON_ERROR); }
require __DIR__ . '/../wordpress/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php';

function verify(bool $ok, string $message): void {
    if (!$ok) throw new RuntimeException($message);
}
try {
    verify(rp_board_section_file('governance', 'Bylaws.pdf') !== null, 'Governance PDF allowed');
    verify(rp_board_section_file('treasury', '2026-Q4.xlsx') !== null, 'Treasury XLSX allowed');
    verify(rp_board_section_file('governance', '2026-Q4.xlsx') === null, 'Cross-section access rejected');
    verify(rp_board_section_file('governance', '../outside.pdf') === null, 'Traversal rejected');
    verify(rp_board_section_file('governance', 'shortcut.pdf') === null, 'Symlink rejected');
    verify(rp_board_section_file('other', 'Bylaws.pdf') === null, 'Unknown section rejected');
    verify(rp_board_section_decode('bad!') === null, 'Bad token rejected');
    $token = rp_board_section_encode('governance', 'Bylaws.pdf');
    verify(rp_board_section_decode($token) === ['governance', 'Bylaws.pdf'], 'Valid token');
    verify(rp_board_section_decode(rp_board_section_encode('other','Bylaws.pdf')) === null, 'Unsupported section token');

    $doc = ['schema_version'=>1,
        'source'=>'rooted-psyche-corporate-record-book/chapters/11-board-editable-document-register.md',
        'documents'=>[['title'=>'Working draft','url'=>'https://docs.google.com/document/d/abc123/edit?usp=sharing','status'=>'Proposed']]];
    file_put_contents($root . '/working-documents.json', json_encode($doc));
    verify(count(rp_board_working_documents()['documents']) === 1, 'Valid BookWorks manifest');
    $doc['documents'][0]['url'] = 'https://untrusted.example/file';
    file_put_contents($root . '/working-documents.json', json_encode($doc));
    verify(rp_board_working_documents() === null, 'Untrusted URL rejected');
    echo "Board supplements resolver checks passed\n";
} finally {
    unlink($root . '/Governance Documents/shortcut.pdf');
    unlink($root . '/Governance Documents/Bylaws.pdf');
    unlink($root . '/Treasury Reports/2026-Q4.xlsx');
    unlink($root . '/working-documents.json');
    unlink($root . '/outside.pdf');
    rmdir($root . '/Governance Documents');
    rmdir($root . '/Treasury Reports');
    rmdir($root);
}
