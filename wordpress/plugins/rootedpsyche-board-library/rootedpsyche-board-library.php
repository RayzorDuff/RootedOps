<?php
/**
 * Plugin Name: Rooted Psyche Board Meeting Library
 * Description: Read-only, role-gated directory listing and downloads for board meeting materials.
 * Version: 0.1.0
 * Requires PHP: 8.1
 * License: GPL-2.0-or-later
 *
 * Deploy with the RootedOps read-only Docker mount. No public media uploads.
 */
defined('ABSPATH') || exit;

const RP_BOARD_LIBRARY_ROOT = '/srv/rootedpsyche-board-meetings';
const RP_BOARD_LIBRARY_MAX_BYTES = 30 * 1024 * 1024;

function rp_board_library_authorized(): bool {
    if (!is_user_logged_in()) {
        return false;
    }
    $user = wp_get_current_user();
    $roles = (array) $user->roles;
    return in_array('administrator', $roles, true)
        || in_array('board_director', $roles, true);
}

function rp_board_library_no_cache(): void {
    if (!headers_sent()) {
        nocache_headers();
        header('Cache-Control: private, no-store, max-age=0, must-revalidate', true);
        header('X-Robots-Tag: noindex, nofollow, noarchive', true);
    }
}

function rp_board_library_extension_allowed(string $filename): bool {
    return in_array(strtolower(pathinfo($filename, PATHINFO_EXTENSION)),
        ['pdf', 'docx', 'xlsx', 'odt', 'ods', 'txt'], true);
}

/** Only direct files in canonical YYYY-MM-DD directories are visible. */
function rp_board_library_file(string $date, string $name): ?string {
    if (!preg_match('/^20[0-9]{2}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])$/D', $date)) {
        return null;
    }
    $parts = explode('-', $date);
    if (!checkdate((int)$parts[1], (int)$parts[2], (int)$parts[0])) {
        return null;
    }
    if ($name === '' || $name === '.' || $name === '..'
        || str_contains($name, '/') || str_contains($name, '\\')
        || str_contains($name, "\0") || !rp_board_library_extension_allowed($name)) {
        return null;
    }
    $root = realpath(RP_BOARD_LIBRARY_ROOT);
    if ($root === false || !is_dir($root) || is_link(RP_BOARD_LIBRARY_ROOT)) {
        return null;
    }
    $directory = RP_BOARD_LIBRARY_ROOT . '/' . $date;
    $canonical_directory = realpath($directory);
    if ($canonical_directory === false || is_link($directory)
        || $canonical_directory !== $root . '/' . $date) {
        return null;
    }
    $path = $directory . '/' . $name;
    if (is_link($path) || !is_file($path) || !is_readable($path)) {
        return null;
    }
    $canonical_file = realpath($path);
    if ($canonical_file === false || $canonical_file !== $canonical_directory . '/' . $name) {
        return null;
    }
    $size = filesize($path);
    if ($size === false || $size < 0 || $size > RP_BOARD_LIBRARY_MAX_BYTES) {
        return null;
    }
    return $path;
}

function rp_board_library_dates(): array {
    $root = RP_BOARD_LIBRARY_ROOT;
    if (is_link($root) || !is_dir($root) || !is_readable($root)) {
        return [];
    }
    $names = scandir($root);
    if ($names === false) {
        return [];
    }
    $dates = [];
    foreach ($names as $date) {
        if (preg_match('/^20[0-9]{2}-[0-9]{2}-[0-9]{2}$/D', $date)
            && is_dir($root . '/' . $date)
            && !is_link($root . '/' . $date)) {
            $parts = explode('-', $date);
            if (checkdate((int)$parts[1], (int)$parts[2], (int)$parts[0])) {
                $dates[] = $date;
            }
        }
    }
    rsort($dates, SORT_STRING);
    return $dates;
}

function rp_board_library_encode_file(string $date, string $name): string {
    return rtrim(strtr(base64_encode(wp_json_encode([$date, $name])), '+/', '-_'), '=');
}

function rp_board_library_decode_file(string $value): ?array {
    if (strlen($value) > 2048 || !preg_match('/^[A-Za-z0-9_-]+$/D', $value)) {
        return null;
    }
    $decoded = base64_decode(strtr($value, '-_', '+/'), true);
    if ($decoded === false) {
        return null;
    }
    $items = json_decode($decoded, true);
    return is_array($items) && count($items) === 2
        && isset($items[0], $items[1])
        && is_string($items[0]) && is_string($items[1])
        ? $items : null;
}

add_action('template_redirect', function (): void {
    if (!isset($_GET['rp_board_download'])) {
        return;
    }
    rp_board_library_no_cache();
    if (!rp_board_library_authorized()) {
        status_header(403);
        exit;
    }
    $encoded = $_GET['rp_board_download'];
    $parts = is_string($encoded) ? rp_board_library_decode_file($encoded) : null;
    $file = $parts ? rp_board_library_file($parts[0], $parts[1]) : null;
    if ($file === null) {
        status_header(404);
        exit;
    }
    // A second size check immediately before serving; no user-controlled paths.
    $size = filesize($file);
    if ($size === false || $size > RP_BOARD_LIBRARY_MAX_BYTES) {
        status_header(404);
        exit;
    }
    status_header(200);
    header('Content-Type: application/octet-stream');
    header('Content-Disposition: attachment; filename="board-document"; filename*=UTF-8\'\'' . rawurlencode(basename($file)));
    header('X-Content-Type-Options: nosniff');
    header('Content-Length: ' . $size);
    $handle = fopen($file, 'rb');
    if ($handle === false) {
        exit;
    }
    fpassthru($handle);
    fclose($handle);
    exit;
}, 0);

add_shortcode('rootedpsyche_board_meetings', function (): string {
    if (!rp_board_library_authorized()) {
        return '<p>Board access is required.</p>';
    }
    rp_board_library_no_cache();
    if (!is_dir(RP_BOARD_LIBRARY_ROOT) || !is_readable(RP_BOARD_LIBRARY_ROOT)) {
        return '<p>Meeting documents are temporarily unavailable.</p>';
    }
    $dates = rp_board_library_dates();
    if (!$dates) {
        return '<p>No meeting documents are available yet.</p>';
    }
    $html = '<section class="rp-board-meetings"><h2>Meeting documents</h2>';
    foreach ($dates as $date) {
        $entries = scandir(RP_BOARD_LIBRARY_ROOT . '/' . $date);
        if ($entries === false) {
            continue;
        }
        $links = [];
        foreach ($entries as $filename) {
            if (rp_board_library_file($date, $filename) === null) {
                continue;
            }
            $token = rp_board_library_encode_file($date, $filename);
            $url = add_query_arg('rp_board_download', rawurlencode($token), home_url('/'));
            $links[] = '<li><a rel="nofollow" href="' . esc_url($url) . '">'
                . esc_html($filename) . '</a></li>';
        }
        $html .= '<h3>' . esc_html(wp_date('F j, Y', strtotime($date . ' 12:00:00'))) . '</h3>';
        $html .= $links
            ? '<ul>' . implode('', $links) . '</ul>'
            : '<p>No downloadable documents available.</p>';
    }
    return $html . '</section>';
});
