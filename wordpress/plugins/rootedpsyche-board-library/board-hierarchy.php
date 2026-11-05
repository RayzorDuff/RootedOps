<?php
/** Additional curated Board Portal hierarchy. Load after board-sections.php. */
defined('ABSPATH') || exit;

function rp_board_hierarchy_root(string $section): ?string {
    $names = [
        'governance' => 'Governance Documents',
        'resolutions' => 'Board Resolutions',
    ];
    if (!isset($names[$section])) return null;
    $root = realpath(RP_BOARD_SUPPLEMENTS_ROOT);
    if ($root === false || is_link(RP_BOARD_SUPPLEMENTS_ROOT) || !is_dir($root)) return null;
    $path = RP_BOARD_SUPPLEMENTS_ROOT . '/' . $names[$section];
    if (is_link($path)) return null;
    $real = realpath($path);
    return $real && is_dir($real) && $real === $root . '/' . $names[$section] ? $real : null;
}

/** Reject traversal, symlinks (all path segments), malformed and hidden paths. */
function rp_board_hierarchy_resolve(string $section, string $relative): ?string {
    $root = rp_board_hierarchy_root($section);
    if (!$root || $relative === '' || strlen($relative) > 1024) return null;
    $parts = explode('/', $relative);
    if (count($parts) > 8) return null;
    $cursor = $root;
    foreach ($parts as $part) {
        if ($part === '' || $part === '.' || $part === '..' || str_starts_with($part, '.')
            || str_contains($part, '\\') || str_contains($part, "\0")) return null;
        $next = $cursor . '/' . $part;
        if (is_link($next)) return null;
        $resolved = realpath($next);
        if (!$resolved || $resolved !== $next) return null;
        $cursor = $resolved;
    }
    if (!is_file($cursor) || !is_readable($cursor) || !rp_board_library_extension_allowed(basename($cursor))) return null;
    $size = filesize($cursor);
    if ($size === false || $size < 0 || $size > RP_BOARD_LIBRARY_MAX_BYTES) return null;
    return $cursor;
}

function rp_board_hierarchy_encode(string $section, string $relative): string {
    return rtrim(strtr(base64_encode(wp_json_encode([$section, $relative])), '+/', '-_'), '=');
}
function rp_board_hierarchy_decode(string $token): ?array {
    if (strlen($token) > 2048 || !preg_match('/^[A-Za-z0-9_-]+$/D', $token)) return null;
    $data = base64_decode(strtr($token, '-_', '+/'), true);
    if ($data === false) return null;
    $parts = json_decode($data, true);
    return is_array($parts) && array_is_list($parts) && count($parts) === 2
        && in_array($parts[0], ['governance', 'resolutions'], true)
        && is_string($parts[1]) ? $parts : null;
}

add_action('template_redirect', function (): void {
    if (!isset($_GET['rp_board_hierarchy_download'])) return;
    rp_board_library_no_cache();
    if (!rp_board_library_authorized()) { status_header(403); exit; }
    $raw = $_GET['rp_board_hierarchy_download'];
    $parts = is_string($raw) ? rp_board_hierarchy_decode($raw) : null;
    $path = $parts ? rp_board_hierarchy_resolve($parts[0], $parts[1]) : null;
    if (!$path) { status_header(404); exit; }
    $stream = fopen($path, 'rb');
    if (!$stream) { status_header(404); exit; }
    $stats = fstat($stream);
    if (!$stats || $stats['size'] < 0 || $stats['size'] > RP_BOARD_LIBRARY_MAX_BYTES) {
        fclose($stream);
        status_header(404);
        exit;
    }
    status_header(200);
    header('Content-Type: application/octet-stream');
    header('Content-Disposition: attachment; filename="board-document"; filename*=UTF-8\'\'' . rawurlencode(basename($path)));
    header('Content-Length: ' . $stats['size']);
    header('X-Content-Type-Options: nosniff');
    fpassthru($stream);
    fclose($stream);
    exit;
}, 0);

/** Bounded listing: maximum 250 eligible files, 8 directory levels; no links. */
function rp_board_hierarchy_list(string $section): string {
    if (!rp_board_library_authorized()) return '<p>Board access is required.</p>';
    rp_board_library_no_cache();
    $root = rp_board_hierarchy_root($section);
    $heading = $section === 'resolutions' ? 'Board Resolutions' : 'Governance Documents';
    if (!$root) return '<p>Documents are temporarily unavailable.</p>';
    $count = 0;
    $walk = function (string $relative, int $depth) use (&$walk, &$count, $root, $section): string {
        if ($depth > 7 || $count >= 250) return '';
        $dir = $root . ($relative === '' ? '' : '/' . $relative);
        $entries = scandir($dir);
        if ($entries === false) return '';
        $html = '';
        foreach ($entries as $name) {
            if ($count >= 250) break;
            if ($name === '.' || $name === '..' || str_starts_with($name, '.')
                || str_contains($name, '\\')) continue;
            $path = $dir . '/' . $name;
            if (is_link($path)) continue;
            $item = ltrim($relative . '/' . $name, '/');
            if (is_dir($path) && realpath($path) === $path && $depth < 7) {
                $child = $walk($item, $depth + 1);
                if ($child !== '') {
                    $html .= '<li><strong>' . esc_html($name) . '</strong><ul>' . $child . '</ul></li>';
                }
            } elseif (rp_board_hierarchy_resolve($section, $item) !== null) {
                $url = add_query_arg('rp_board_hierarchy_download',
                    rp_board_hierarchy_encode($section, $item), home_url('/'));
                $html .= '<li><a rel="nofollow" href="' . esc_url($url) . '">' . esc_html($name) . '</a></li>';
                $count++;
            }
        }
        return $html;
    };
    $links = $walk('', 0);
    return '<section class="rp-board-hierarchy"><h2>' . esc_html($heading) . '</h2>'
        . ($links ? '<ul>' . $links . '</ul>' : '<p>No documents available yet.</p>') . '</section>';
}

// Override the existing flat Governance shortcode, retaining its name.
add_shortcode('rootedpsyche_board_governance', fn(): string => rp_board_hierarchy_list('governance'));
add_shortcode('rootedpsyche_board_resolutions', fn(): string => rp_board_hierarchy_list('resolutions'));
