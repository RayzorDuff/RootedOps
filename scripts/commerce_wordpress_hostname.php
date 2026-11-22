<?php
// wp eval-file; changes only reviewed storefront content, never options/meta/orders/GUIDs.
if (!defined('ABSPATH')) exit;
$mode = $args[0] ?? 'preview';
$journal = $args[1] ?? '';
if (!in_array($mode, array('preview', 'apply', 'restore'), true)) throw new InvalidArgumentException('preview, apply or restore required');
function rootedops_domain_content($value) {
    if (is_object($value)) throw new RuntimeException('Serialized object needs manual content review');
    if (is_string($value) && is_serialized($value)) {
        return serialize(rootedops_domain_content(unserialize($value, array('allowed_classes' => false))));
    }
    if (is_array($value)) return array_map('rootedops_domain_content', $value);
    if (!is_string($value)) return $value;
    return preg_replace('~https://shop-test[.]danks[.]store(?=[/?#\s"\x27<>]|$)~', 'https://dankmushrooms.net', $value);
}
if ($mode !== 'preview') {
    $parent = realpath(dirname($journal));
    $webroot = realpath(ABSPATH);
    if (!$parent || $journal !== $parent . '/' . basename($journal)
        || ($parent === $webroot || str_starts_with($parent, $webroot . '/'))
        || (fileperms($parent) & 0077)) throw new RuntimeException('Journal requires an absolute private directory outside WordPress, mode 0700');
}
global $wpdb;
$types = array('post','page','product','product_variation','wp_block','wp_template','wp_template_part');
$changed = array();
$wpdb->query('START TRANSACTION');
try {
    if ($mode === 'restore') {
        if (!is_file($journal) || (fileperms($journal) & 0077)) throw new RuntimeException('Private journal required');
        $entries = json_decode(file_get_contents($journal), true, 512, JSON_THROW_ON_ERROR);
        foreach ($entries as $entry) {
            $id = (int) $entry['id'];
            $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$wpdb->posts} WHERE ID=%d FOR UPDATE", $id), ARRAY_A);
            if (!$row || !in_array($row['post_type'], $types, true)) throw new RuntimeException('Content type changed: stop for review');
            foreach ($entry['after'] as $column => $value) {
                if (!in_array($column, array('post_content','post_excerpt'), true) || $row[$column] !== $value
                    || !array_key_exists($column, $entry['before'])) throw new RuntimeException('Content changed since migration: stop for review');
            }
            if (array_keys($entry['before']) !== array_keys($entry['after'])) throw new RuntimeException('Invalid journal');
            if ($wpdb->update($wpdb->posts, $entry['before'], array('ID' => $id)) === false) throw new RuntimeException('Restore failed');
            $changed[] = $entry;
        }
    } else {
        $rows = $wpdb->get_results("SELECT ID,post_content,post_excerpt FROM {$wpdb->posts}
            WHERE post_type IN ('post','page','product','product_variation','wp_block','wp_template','wp_template_part')
            AND post_status<>'auto-draft' FOR UPDATE", ARRAY_A);
        if ($wpdb->last_error) throw new RuntimeException('Content read failed');
        foreach ($rows as $row) {
            $values = $before = array();
            foreach (array('post_content', 'post_excerpt') as $column) {
                $replacement = rootedops_domain_content($row[$column]);
                if ($replacement !== $row[$column]) { $values[$column] = $replacement; $before[$column] = $row[$column]; }
            }
            if (!$values) continue;
            $changed[] = array('id' => (int) $row['ID'], 'before' => $before, 'after' => $values);
            if ($mode === 'apply' && $wpdb->update($wpdb->posts, $values, array('ID' => $row['ID'])) === false) throw new RuntimeException('Content update failed');
        }
        if ($mode === 'apply') {
            $encoded = json_encode($changed, JSON_THROW_ON_ERROR);
            umask(0077);
            $handle = fopen($journal, 'x'); // Exclusive: never overwrite the recovery journal.
            if (!$handle) throw new RuntimeException('Use a new private journal filename');
            chmod($journal, 0600);
            if (fwrite($handle, $encoded) !== strlen($encoded) || !fflush($handle) || !fsync($handle)) throw new RuntimeException('Journal write failed');
            fclose($handle);
        }
    }
    if ($wpdb->query($mode === 'preview' ? 'ROLLBACK' : 'COMMIT') === false) throw new RuntimeException('Transaction failed; retain journal for review');
    foreach ($changed as $entry) clean_post_cache($entry['id']);
    echo $mode . ' changed_content_rows=' . count($changed) . "\n";
} catch (Throwable $error) {
    $wpdb->query('ROLLBACK');
    throw $error;
}
