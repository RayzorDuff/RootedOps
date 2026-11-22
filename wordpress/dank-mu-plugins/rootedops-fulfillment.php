<?php
/** Plugin Name: RootedOps MushroomProcess fulfillment
 * Enabled by private ROOTEDOPS_MP_WOO_ENABLED and application-password permissions.
 */
defined('ABSPATH') || exit;

function rootedops_mp_enabled() {
    return defined('ROOTEDOPS_MP_WOO_ENABLED') && ROOTEDOPS_MP_WOO_ENABLED === true;
}

// Hold the same mutex through the whole request, including native stock markers.
// Product hooks cover checkout, stock restoration, refunds and admin corrections.
function rootedops_mp_lock() {
    global $wpdb;
    static $held = false;
    if (!rootedops_mp_enabled() || $held) return;
    $name = 'rootedops_mp_' . get_current_blog_id();
    if ((int) $wpdb->get_var($wpdb->prepare('SELECT GET_LOCK(%s, 15)', $name)) !== 1) {
        // Woo 11.2 catches Exception during save and can still emit status hooks.
        // Error must escape that path so a failed lock cannot become a write.
        throw new Error('Inventory publication busy. Retry this operation.');
    }
    $held = true;
    register_shutdown_function(function () use ($wpdb, $name) {
        $wpdb->get_var($wpdb->prepare('SELECT RELEASE_LOCK(%s)', $name));
    });
}
add_action('woocommerce_before_order_object_save', 'rootedops_mp_lock', -1000);
add_action('woocommerce_product_before_set_stock', 'rootedops_mp_lock', -1000);
add_action('woocommerce_variation_before_set_stock', 'rootedops_mp_lock', -1000);

function rootedops_mp_completion_proof($order) {
    $counts = array();
    foreach (($order->get_meta('_rootedops_mp_shipments', true) ?: array()) as $row) {
        foreach ($row['lines'] as $line) {
            $id = (string) $line['line_id'];
            $counts[$id] = ($counts[$id] ?? 0) + $line['quantity'];
        }
    }
    foreach ($order->get_items() as $id => $item) {
        if (($counts[(string) $id] ?? 0) !== (int) $item->get_quantity()) {
            return false;
        }
    }
    return true;
}
function rootedops_mp_guard_completion($order) {
    if (!rootedops_mp_enabled() || !defined('ROOTEDOPS_MP_WOO_CUTOFF')
        || !$order->get_date_created() || $order->get_date_created()->getTimestamp() < ROOTEDOPS_MP_WOO_CUTOFF
        || ($order->get_changes()['status'] ?? '') !== 'completed') return;
    if (!rootedops_mp_completion_proof($order)) {
        throw new Error('Complete dispatch in MushroomProcess before completing this Woo order.');
    }
}
add_action('woocommerce_before_order_object_save', 'rootedops_mp_guard_completion', -900);
add_action('woocommerce_order_status_completed', function ($id) {
    if (!rootedops_mp_enabled() || !defined('ROOTEDOPS_MP_WOO_CUTOFF')) return;
    $saved = new WC_Order($id);
    if (!$saved->get_date_created() || $saved->get_date_created()->getTimestamp() < ROOTEDOPS_MP_WOO_CUTOFF) return;
    if (!$saved->has_status('completed') || !rootedops_mp_completion_proof($saved)) {
        throw new Error('Woo completion failed. Retry the same movement.');
    }
}, -1000);

// Release stock only when the cancellation has reached MP. This also protects a
// dispatched package whose Woo acknowledgment is still retrying after a timeout.
function rootedops_mp_native_restore($allowed, $order) {
    if (rootedops_mp_enabled() && defined('ROOTEDOPS_MP_WOO_CUTOFF') && $order->get_date_created()
        && $order->get_date_created()->getTimestamp() >= ROOTEDOPS_MP_WOO_CUTOFF) return false;
    return $allowed;
}
add_filter('woocommerce_can_restore_order_stock', 'rootedops_mp_native_restore', 10, 2);
add_filter('woocommerce_can_restock_refunded_items', 'rootedops_mp_native_restore', 10, 2);

function rootedops_mp_tracking_details($order) {
    $shipments = $order->get_meta('_rootedops_mp_shipments', true) ?: array();
    $shipments = array_filter($shipments, function ($row) {
        return !empty($row['tracking']['tracking_number']) && ($row['tracking']['label_status'] ?? '') !== 'voided';
    });
    if (!$shipments) return;
    echo '<h2>' . esc_html__('Shipment tracking', 'rootedops') . '</h2><ul>';
    foreach ($shipments as $row) {
        $t = $row['tracking'];
        if (empty($t['tracking_number'])) continue;
        echo '<li>' . esc_html(trim(($t['carrier'] ?? '') . ' ' . ($t['service'] ?? '') . ' ' . $t['tracking_number'])) . '</li>';
    }
    echo '</ul>';
}
add_action('woocommerce_order_details_after_order_table', 'rootedops_mp_tracking_details');
add_action('woocommerce_email_after_order_table', function ($order, $sent_to_admin, $plain_text, $email) {
    if (!$email || $email->id !== 'customer_completed_order') return;
    if ($plain_text) {
        foreach (($order->get_meta('_rootedops_mp_shipments', true) ?: array()) as $row) {
            $t = $row['tracking'];
            if (empty($t['tracking_number']) || ($t['label_status'] ?? '') === 'voided') continue;
            echo sanitize_text_field(trim(($t['carrier'] ?? '') . ' ' . ($t['service'] ?? '') . ' ' . ($t['tracking_number'] ?? ''))) . "\n";
        }
    } else rootedops_mp_tracking_details($order);
}, 10, 4);

function rootedops_mp_permissions() {
    return rootedops_mp_enabled() && current_user_can('manage_woocommerce');
}

function rootedops_mp_order($id) {
    $order = wc_get_order($id);
    if (!$order || $order->get_type() !== 'shop_order') throw new InvalidArgumentException('Unknown Woo order');
    return $order;
}

function rootedops_mp_identity($request) {
    $order = rootedops_mp_order((int) $request['id']);
    return array('id' => $order->get_id(), 'edit_url' => $order->get_edit_order_url(),
        'status' => $order->get_status());
}

function rootedops_mp_save_order($order) {
    $order->save();
    if (method_exists($order, 'get_last_save_error') && $order->get_last_save_error() !== null) {
        throw new RuntimeException('Woo order save failed. Retry the same movement.');
    }
    $saved = new WC_Order($order->get_id());
    $saved->read_meta_data(true);
    if ($saved->get_meta('_rootedops_mp_shipments', true) !== $order->get_meta('_rootedops_mp_shipments', true)) {
        throw new RuntimeException('Woo movement proof did not persist. Retry the same movement.');
    }
}

function rootedops_mp_shipment($request) {
    rootedops_mp_lock();
    $p = $request->get_json_params();
    $order = rootedops_mp_order((int) $request['id']);
    $reference = $p['reference'] ?? '';
    if (!is_string($reference) || !preg_match('/^[A-Za-z0-9_.:-]{1,120}$/D', $reference)
        || empty($p['lines']) || !is_array($p['lines'])) throw new InvalidArgumentException('Movement and lines required');
    $stored = $order->get_meta('_rootedops_mp_shipments', true) ?: array();
    $digest = hash('sha256', wp_json_encode(array('reference' => $reference, 'lines' => $p['lines'])));
    if (isset($stored[$reference])) {
        if ($stored[$reference]['digest'] !== $digest) throw new InvalidArgumentException('Movement changed');
        if ($stored[$reference]['tracking'] !== ($p['tracking'] ?? array())) {
            $stored[$reference]['tracking'] = $p['tracking'] ?? array();
            $order->update_meta_data('_rootedops_mp_shipments', $stored);
            rootedops_mp_save_order($order);
        }
        if ($stored[$reference]['complete'] && $order->has_status('processing')) {
            if (!$order->update_status('completed', 'Dispatch confirmed by MushroomProcess')) {
                throw new RuntimeException('Woo completion failed. Retry the same movement.');
            }
        }
        return array('status' => 'duplicate', 'order_status' => $order->get_status());
    }
    if (!in_array($order->get_status(), array('processing', 'completed'), true)
        || $order->get_total_refunded() > 0) throw new InvalidArgumentException('Order needs fulfillment review');
    $counts = array();
    foreach ($stored as $row) foreach ($row['lines'] as $line) {
        $id = (string) $line['line_id'];
        $counts[$id] = ($counts[$id] ?? 0) + $line['quantity'];
    }
    foreach ($p['lines'] as $line) {
        $id = (string) ($line['line_id'] ?? '');
        $item = $order->get_item((int) $id);
        $qty = $line['quantity'] ?? 0;
        if (!$item || !($item instanceof WC_Order_Item_Product) || !is_int($qty) || $qty <= 0
            || ($counts[$id] ?? 0) + $qty > $item->get_quantity()) throw new InvalidArgumentException('Shipment quantity mismatch');
        $counts[$id] = ($counts[$id] ?? 0) + $qty;
    }
    $complete = true;
    foreach ($order->get_items() as $id => $item) {
        if (($counts[(string) $id] ?? 0) !== (int) $item->get_quantity()) $complete = false;
    }
    $tracking = $p['tracking'] ?? array();
    $stored[$reference] = array('digest' => $digest, 'lines' => $p['lines'], 'tracking' => $tracking, 'complete' => $complete);
    $order->update_meta_data('_rootedops_mp_shipments', $stored);
    // Save durable movement proof before completion. Retry can finish completion below.
    rootedops_mp_save_order($order);
    if ($complete && !$order->has_status('completed')
        && !$order->update_status('completed', 'Dispatch confirmed by MushroomProcess')) {
        throw new RuntimeException('Woo completion failed. Retry the same movement.');
    }
    return array('status' => 'recorded', 'order_status' => $order->get_status());
}

// Quantity already deducted by Woo but not represented by an MP hold or shipment.
function rootedops_mp_publish_quantity($available, $reduced, $represented) {
    if (!is_int($available) || $available < 0) throw new InvalidArgumentException('Invalid MP availability');
    if (!is_array($represented)) throw new InvalidArgumentException('Explicit MP order-line coverage required');
    foreach ($represented as $key => $quantity) {
        if (!preg_match('/^[1-9][0-9]*:[1-9][0-9]*$/D', $key) || !is_int($quantity) || $quantity < 0) {
            throw new InvalidArgumentException('Invalid MP order-line coverage');
        }
    }
    $missing = 0;
    foreach ($reduced as $key => $quantity) $missing += max(0, $quantity - ($represented[$key] ?? 0));
    foreach ($represented as $key => $quantity) {
        if ($quantity > 0 && !array_key_exists($key, $reduced)) {
            throw new InvalidArgumentException('MP commitment awaits Woo stock reduction or cancellation intake');
        }
    }
    return max(0, $available - $missing);
}

function rootedops_mp_stock($request) {
    rootedops_mp_lock();
    $p = $request->get_json_params();
    if (!defined('ROOTEDOPS_MP_WOO_CUTOFF') || !is_int(ROOTEDOPS_MP_WOO_CUTOFF)) {
        throw new InvalidArgumentException('Explicit Woo order creation cutoff required');
    }
    if (!isset($p['revision']) || !is_int($p['revision']) || empty($p['products'])) throw new InvalidArgumentException('Snapshot revision and products required');
    $previous = (int) get_option('rootedops_mp_inventory_revision', 0);
    if ($p['revision'] <= $previous) return array('status' => 'stale');
    $products = array();
    $reduced = array();
    foreach ($p['products'] as $row) {
        $id = (int) $row['woo_id'];
        $product = wc_get_product($id);
        $owner = $product && $product->get_parent_id() ? wc_get_product($product->get_parent_id()) : $product;
        if (!$product || !$owner || $owner->get_status() !== 'publish' || $product->get_status() !== 'publish'
            || $product->get_sku() !== $row['sku'] || !$product->get_manage_stock()
            || $product->get_parent_id() !== (int) ($row['parent_woo_id'] ?? 0)
            || $product->get_stock_managed_by_id() !== $id || $product->get_backorders() !== 'no'
            || $owner->get_meta('_rootedops_source_key', true) !== $row['source_key']
            || isset($products[$id])) throw new InvalidArgumentException('Exact published stock ownership required');
        $products[$id] = array('product' => $product, 'row' => $row);
        $reduced[$id] = array();
    }
    $page = 1;
    do {
        $orders = wc_get_orders(array('limit' => 100, 'page' => $page++, 'paginate' => true,
            'type' => 'shop_order', 'date_created' => '>=' . (int) ROOTEDOPS_MP_WOO_CUTOFF));
        foreach ($orders->orders as $order) foreach ($order->get_items() as $line_id => $item) {
            $id = $item->get_variation_id() ?: $item->get_product_id();
            if (!isset($products[$id])) continue;
            $qty = (int) $item->get_meta('_reduced_stock', true);
            $terminal = $order->has_status(array('cancelled', 'failed', 'refunded'));
            if ($qty > 0 || $terminal) $reduced[$id][$order->get_id() . ':' . $line_id] = $terminal ? 0 : $qty;
        }
    } while ($page <= $orders->max_num_pages);
    // Validate the whole snapshot before changing the first quantity.
    foreach ($products as $id => &$entry) {
        $entry['quantity'] = rootedops_mp_publish_quantity($entry['row']['available'], $reduced[$id], $entry['row']['represented']);
    }
    unset($entry);
    foreach ($products as $entry) {
        $written = wc_update_product_stock($entry['product'], $entry['quantity'], 'set');
        if (is_wp_error($written) || $written === false || $written === null || (int) $written !== $entry['quantity']) {
            throw new RuntimeException('Woo stock write failed. Retry publication.');
        }
    }
    if (!update_option('rootedops_mp_inventory_revision', $p['revision'], false)
        && (int) get_option('rootedops_mp_inventory_revision') !== $p['revision']) {
        throw new RuntimeException('Woo inventory receipt save failed. Retry publication.');
    }
    return array('status' => 'published', 'count' => count($products), 'revision' => $p['revision']);
}

// A cash receipt is independent of physical dispatch and processor captures.
function rootedops_mp_cash_receipt($request) {
    if (!defined('ROOTEDOPS_MP_CASH_ENABLED') || ROOTEDOPS_MP_CASH_ENABLED !== true) {
        throw new InvalidArgumentException('Cash receipt projection disabled');
    }
    rootedops_mp_lock();
    $p = $request->get_json_params();
    $order = rootedops_mp_order((int) $request['id']);
    if (!defined('ROOTEDOPS_MP_WOO_CUTOFF') || !$order->get_date_created()
        || $order->get_date_created()->getTimestamp() < ROOTEDOPS_MP_WOO_CUTOFF
        || $order->get_payment_method() !== 'cod' || $order->get_total_refunded() > 0
        || !$order->has_status(array('pending', 'on-hold', 'processing', 'completed'))
        || !preg_match('/^[0-9a-f-]{36}$/D', $p['receipt_id'] ?? '')
        || $order->get_currency() !== ($p['currency'] ?? '')
        || wc_format_decimal($order->get_total(), 2) !== wc_format_decimal($p['amount'] ?? '-1', 2)) {
        throw new InvalidArgumentException('Exact active COD order, receipt and amount required');
    }
    $stored = $order->get_meta('_rootedops_mp_cash_receipt', true);
    if ($stored && $stored !== $p) throw new InvalidArgumentException('Cash receipt identity changed');
    if (!$stored) {
        $order->update_meta_data('_rootedops_mp_cash_receipt', $p);
        $order->save();
        $saved = new WC_Order($order->get_id());
        if ($saved->get_meta('_rootedops_mp_cash_receipt', true) !== $p) {
            throw new RuntimeException('Cash receipt save failed; retry same receipt');
        }
    }
    // Never call payment_complete(): virtual-only orders could complete before MP dispatch.
    if ($order->has_status(array('pending', 'on-hold'))) {
        if (!$order->get_date_paid()) $order->set_date_paid(time());
        if (!$order->update_status('processing', 'Cash received; ERP receipt linked by MushroomProcess')) {
            throw new RuntimeException('Cash status projection failed; retry same receipt');
        }
    }
    return array('status' => $stored ? 'duplicate' : 'recorded', 'order_status' => $order->get_status());
}

add_action('rest_api_init', function () {
    foreach (array(
        array('/orders/(?P<id>[1-9][0-9]*)/edit-link', 'GET', 'rootedops_mp_identity'),
        array('/orders/(?P<id>[1-9][0-9]*)/shipments', 'POST', 'rootedops_mp_shipment'),
        array('/orders/(?P<id>[1-9][0-9]*)/cash-receipt', 'POST', 'rootedops_mp_cash_receipt'),
        array('/inventory', 'POST', 'rootedops_mp_stock')
    ) as $route) register_rest_route('rootedops/v1', $route[0], array(
        'methods' => $route[1], 'permission_callback' => 'rootedops_mp_permissions',
        'callback' => function ($request) use ($route) {
            try { return call_user_func($route[2], $request); }
            catch (Throwable $e) { return new WP_Error('mp_review', $e->getMessage(), array('status' => 409)); }
        }
    ));
});
