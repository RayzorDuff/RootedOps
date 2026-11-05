<?php
/**
 * Additional sections for Rooted Psyche Board Meeting Library v0.2.
 *
 * A separate read-only BookWorksSupplements mount makes the meeting library
 * backward compatible. Never serve arbitrary server paths or the whole mount.
 */
defined('ABSPATH') || exit;
defined('RP_BOARD_SUPPLEMENTS_ROOT') || define('RP_BOARD_SUPPLEMENTS_ROOT', '/srv/rootedpsyche-board-supplements');

function rp_board_section_info(string $section): ?array {
    $map = [
        'governance' => ['Governance Documents', 'Governance Documents'],
        'treasury' => ['Treasury Reports', 'Treasury Reports'],
    ];
    return $map[$section] ?? null;
}

function rp_board_section_directory(string $section): ?string {
    $info = rp_board_section_info($section);
    if (!$info) return null;
    $root = realpath(RP_BOARD_SUPPLEMENTS_ROOT);
    if ($root === false || is_link(RP_BOARD_SUPPLEMENTS_ROOT) || !is_dir($root)) return null;
    $path = RP_BOARD_SUPPLEMENTS_ROOT . '/' . $info[1];
    if (is_link($path)) return null;
    $real = realpath($path);
    return $real !== false && is_dir($real) && $real === $root . '/' . $info[1] ? $real : null;
}

/** Only leaf files explicitly placed directly in the named curated folder. */
function rp_board_section_file(string $section, string $filename): ?string {
    if ($filename === '' || $filename === '.' || $filename === '..'
        || str_contains($filename, '/') || str_contains($filename, '\\')
        || str_contains($filename, "\0") || !rp_board_library_extension_allowed($filename)) {
        return null;
    }
    $dir = rp_board_section_directory($section);
    if ($dir === null) return null;
    $path = $dir . '/' . $filename;
    if (is_link($path) || !is_file($path) || !is_readable($path) || realpath($path) !== $path) {
        return null;
    }
    $bytes = filesize($path);
    if ($bytes === false || $bytes < 0 || $bytes > RP_BOARD_LIBRARY_MAX_BYTES) return null;
    return $path;
}

function rp_board_section_encode(string $section, string $filename): string {
    return rtrim(strtr(base64_encode(wp_json_encode([$section, $filename])), '+/', '-_'), '=');
}

function rp_board_section_decode(string $value): ?array {
    if (strlen($value) > 2048 || !preg_match('/^[A-Za-z0-9_-]+$/D', $value)) return null;
    $decoded = base64_decode(strtr($value, '-_', '+/'), true);
    if ($decoded === false) return null;
    $items = json_decode($decoded, true);
    return is_array($items) && array_is_list($items) && count($items) === 2
        && is_string($items[0]) && is_string($items[1])
        && rp_board_section_info($items[0]) ? $items : null;
}

add_action('template_redirect', function (): void {
    if (!isset($_GET['rp_board_section_download'])) return;
    rp_board_library_no_cache();
    if (!rp_board_library_authorized()) {
        status_header(403);
        exit;
    }
    $token = $_GET['rp_board_section_download'];
    $parts = is_string($token) ? rp_board_section_decode($token) : null;
    $path = $parts ? rp_board_section_file($parts[0], $parts[1]) : null;
    if ($path === null) {
        status_header(404);
        exit;
    }
    $handle = fopen($path, 'rb');
    if (!$handle) {
        status_header(404);
        exit;
    }
    $stats = fstat($handle);
    if (!$stats || $stats['size'] > RP_BOARD_LIBRARY_MAX_BYTES || $stats['size'] < 0) {
        fclose($handle);
        status_header(404);
        exit;
    }
    status_header(200);
    header('Content-Type: application/octet-stream');
    header('Content-Disposition: attachment; filename="board-document"; filename*=UTF-8\'\'' . rawurlencode($parts[1]));
    header('Content-Length: ' . $stats['size']);
    header('X-Content-Type-Options: nosniff');
    fpassthru($handle);
    fclose($handle);
    exit;
}, 0);

function rp_board_render_section(string $section): string {
    if (!rp_board_library_authorized()) return '<p>Board access is required.</p>';
    rp_board_library_no_cache();
    $info = rp_board_section_info($section);
    $dir = rp_board_section_directory($section);
    if (!$info || !$dir) return '<p>Documents are temporarily unavailable.</p>';
    $names = scandir($dir);
    if ($names === false) return '<p>Documents are temporarily unavailable.</p>';
    $links = [];
    foreach ($names as $name) {
        if (rp_board_section_file($section, $name) === null) continue;
        $token = rp_board_section_encode($section, $name);
        $url = add_query_arg('rp_board_section_download', $token, home_url('/'));
        $links[] = '<li><a rel="nofollow" href="' . esc_url($url) . '">' . esc_html($name) . '</a></li>';
    }
    return '<section class="rp-board-files"><h2>' . esc_html($info[0]) . '</h2>'
        . ($links ? '<ul>' . implode('', $links) . '</ul>' : '<p>No documents available yet.</p>')
        . '</section>';
}

add_shortcode('rootedpsyche_board_governance', fn(): string => rp_board_render_section('governance'));
add_shortcode('rootedpsyche_board_treasury', fn(): string => rp_board_render_section('treasury'));

/**
 * Generated by BookWorks from chapters/11-board-editable-document-register.md.
 * This is an export, never a second manually maintained list of Docs URLs.
 */
function rp_board_working_documents(): ?array {
    $root = realpath(RP_BOARD_SUPPLEMENTS_ROOT);
    if ($root === false || is_link(RP_BOARD_SUPPLEMENTS_ROOT)) return null;
    $path = $root . '/working-documents.json';
    if (is_link($path) || !is_file($path) || !is_readable($path) || realpath($path) !== $path) return null;
    if (filesize($path) === false || filesize($path) > 131072) return null;
    $manifest = json_decode(file_get_contents($path), true);
    if (!is_array($manifest) || ($manifest['schema_version'] ?? null) !== 1
        || ($manifest['source'] ?? null) !== 'rooted-psyche-corporate-record-book/chapters/11-board-editable-document-register.md'
        || !is_array($manifest['documents'] ?? null) || count($manifest['documents']) > 100) return null;
    foreach ($manifest['documents'] as $doc) {
        if (!is_array($doc) || !is_string($doc['title'] ?? null)
            || !is_string($doc['url'] ?? null) || !is_string($doc['status'] ?? null)
            || strlen($doc['title']) > 256 || strlen($doc['status']) > 700
            || !preg_match('~^https://docs\\.google\\.com/(?:document|spreadsheets)/d/[a-zA-Z0-9_-]+(?:/edit)?(?:\\?[^#]*)?$~D', $doc['url'])) {
            return null;
        }
    }
    return $manifest;
}

add_shortcode('rootedpsyche_board_working_documents', function (): string {
    if (!rp_board_library_authorized()) return '<p>Board access is required.</p>';
    rp_board_library_no_cache();
    $data = rp_board_working_documents();
    if ($data === null) return '<p>Working documents are temporarily unavailable.</p>';
    $html = '<section class="rp-board-working"><h2>Working Documents</h2><ul>';
    foreach ($data['documents'] as $doc) {
        $html .= '<li><a target="_blank" rel="noopener noreferrer nofollow" href="'
            . esc_url($doc['url']) . '">' . esc_html($doc['title']) . '</a>'
            . ' — ' . esc_html($doc['status']) . '</li>';
    }
    return $html . '</ul></section>';
});
