<?php
// Native, disposable Woo test. Invoke with wp eval-file in the guarded CI fixture.
if (getenv('COMMERCE_NATIVE_WOO_FIXTURE') !== '1') throw new RuntimeException('Disposable Woo required');
function mp_expect($ok, $reason) { if (!$ok) throw new RuntimeException($reason); }
function mp_request($data, $id = null) {
    $request = new WP_REST_Request('POST');
    if ($id) $request['id'] = $id;
    $request->set_header('Content-Type', 'application/json');
    $request->set_body(wp_json_encode($data));
    return $request;
}
update_option('woocommerce_manage_stock', 'yes');
delete_option('rootedops_mp_inventory_revision');
$product = new WC_Product_Simple();
$product->set_name('Disposable MP publication');
$product->set_sku('MP-CI-PUBLISHED');
$product->set_status('publish');
$product->set_regular_price('10');
$product->set_manage_stock(true);
$product->set_stock_quantity(10);
$product->set_backorders('no');
$product->update_meta_data('_rootedops_source_key', 'synthetic:mp');
$id = $product->save();
$order = wc_create_order();
$line = $order->add_product($product, 2);
$order->calculate_totals();
$order->update_status('processing');
mp_expect(wc_get_product($id)->get_stock_quantity() === 8, 'Native checkout deduction');
try {
    $order->set_status('completed');
    rootedops_mp_guard_completion($order);
    throw new RuntimeException('Label completion was accepted before MP dispatch');
} catch (Throwable $error) {
    mp_expect(str_contains($error->getMessage(), 'Complete dispatch in MushroomProcess'), 'Premature completion guard failed');
}
try { $order->save(); } catch (Throwable $error) {
    mp_expect(str_contains($error->getMessage(), 'Complete dispatch in MushroomProcess'), 'Unexpected save failure');
}
$order = wc_get_order($order->get_id());
mp_expect($order->has_status('processing'), 'Completion guard did not protect the saved order');
$snapshot = array('revision' => 1, 'products' => array(array('woo_id' => $id, 'sku' => 'MP-CI-PUBLISHED',
    'source_key' => 'synthetic:mp', 'available' => 8, 'represented' => array($order->get_id() . ':' . $line => 2))));
rootedops_mp_stock(mp_request($snapshot));
mp_expect(wc_get_product($id)->get_stock_quantity() === 8, 'MP hold double deducted');
$late = wc_create_order();
$late->add_product(wc_get_product($id), 1);
$late->calculate_totals();
$late->update_status('processing');
$snapshot['revision']++;
rootedops_mp_stock(mp_request($snapshot));
mp_expect(wc_get_product($id)->get_stock_quantity() === 7, 'Webhook lag restored reserved stock');
$packet = array('reference' => 'synthetic-package-1', 'lines' => array(array('line_id' => (string) $line, 'quantity' => 1)),
    'tracking' => array('carrier' => 'Synthetic carrier', 'tracking_number' => 'SYNTHETIC', 'postage' => '0.00'));
rootedops_mp_shipment(mp_request($packet, $order->get_id()));
mp_expect(wc_get_order($order->get_id())->get_status() === 'processing', 'Partial order completed');
rootedops_mp_shipment(mp_request($packet, $order->get_id()));
$packet['reference'] = 'synthetic-package-2';
$failed_completion = false;
$completion_count = 0;
add_action('woocommerce_before_order_object_save', function ($candidate) use ($order, &$failed_completion) {
    if ($candidate->get_id() === $order->get_id() && ($candidate->get_changes()['status'] ?? '') === 'completed' && !$failed_completion) {
        $failed_completion = true;
        throw new RuntimeException('Synthetic failure before completion save');
    }
}, 500);
add_action('woocommerce_order_status_completed', function ($id) use ($order, &$completion_count) {
    if ($id === $order->get_id()) $completion_count++;
});
try {
    rootedops_mp_shipment(mp_request($packet, $order->get_id()));
    throw new RuntimeException('Failed Woo completion was acknowledged');
} catch (Throwable $error) {
    mp_expect(str_contains($error->getMessage(), 'Woo completion failed'), 'Completion failure not returned for retry');
}
mp_expect(wc_get_order($order->get_id())->has_status('processing'), 'Failed completion changed the persisted status');
rootedops_mp_shipment(mp_request($packet, $order->get_id()));
mp_expect(wc_get_order($order->get_id())->get_status() === 'completed', 'Full order not completed');
mp_expect(wc_get_product($id)->get_stock_quantity() === 7, 'Dispatch deducted Woo stock again');
rootedops_mp_shipment(mp_request($packet, $order->get_id()));
mp_expect($completion_count === 1, 'Completion replay emitted another notification event');
$packet['tracking']['tracking_number'] = 'SYNTHETIC-REPLACEMENT';
rootedops_mp_shipment(mp_request($packet, $order->get_id()));
mp_expect(count(wc_get_order($order->get_id())->get_meta('_rootedops_mp_shipments', true)) === 2, 'Tracking replacement created a movement');
$late->update_status('cancelled');
$snapshot['revision']++;
rootedops_mp_stock(mp_request($snapshot));
mp_expect(wc_get_product($id)->get_stock_quantity() === 8, 'Cancellation quantity drift');
$snapshot['revision']++;
$snapshot['products'][0]['available'] = 11;
rootedops_mp_stock(mp_request($snapshot));
mp_expect(wc_get_product($id)->get_stock_quantity() === 11, 'Replenishment failed');
$snapshot['products'][0]['available'] = 99;
mp_expect(rootedops_mp_stock(mp_request($snapshot))['status'] === 'stale', 'Old snapshot admitted');
mp_expect(wc_get_product($id)->get_stock_quantity() === 11, 'Stale snapshot changed stock');
$parent = new WC_Product_Variable();
$parent->set_name('Disposable MP variable');
$parent->set_status('publish');
$parent->update_meta_data('_rootedops_source_key', 'synthetic:mp-variable');
$parent_id = $parent->save();
$variation = new WC_Product_Variation();
$variation->set_parent_id($parent_id);
$variation->set_status('publish');
$variation->set_sku('MP-CI-VARIATION');
$variation->set_regular_price('10');
$variation->set_manage_stock(true);
$variation->set_stock_quantity(4);
$variation->set_backorders('no');
$variation_id = $variation->save();
$snapshot['revision']++;
$snapshot['products'][0]['available'] = 11;
$snapshot['products'][] = array('woo_id' => $variation_id, 'parent_woo_id' => $parent_id,
    'sku' => 'MP-CI-VARIATION', 'source_key' => 'synthetic:mp-variable', 'available' => 4, 'represented' => array());
rootedops_mp_stock(mp_request($snapshot));
mp_expect(wc_get_product($variation_id)->get_stock_quantity() === 4, 'Published variation failed');
$snapshot['revision']++;
$snapshot['products'][0]['available'] = 77;
$snapshot['products'][1]['parent_woo_id'] = $parent_id + 999;
try {
    rootedops_mp_stock(mp_request($snapshot));
    throw new RuntimeException('Wrong variation parent was accepted');
} catch (InvalidArgumentException $error) {
    mp_expect(wc_get_product($id)->get_stock_quantity() === 11, 'Invalid batch partially changed stock');
}
$link = rootedops_mp_identity(array('id' => $order->get_id()));
mp_expect($link['edit_url'] === wc_get_order($order->get_id())->get_edit_order_url(), 'Generated admin URL differs');
$order->delete(true);
$late->delete(true);
wc_get_product($id)->delete(true);
wc_get_product($variation_id)->delete(true);
wc_get_product($parent_id)->delete(true);
delete_option('rootedops_mp_inventory_revision');
echo "Native Woo publication, webhook lag, partial/full dispatch, cancellation and replay passed.\n";
