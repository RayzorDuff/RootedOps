<?php
// WP-CLI fixture for the disposable native webhook test. No webhook is relayed by hand.
if ( ! defined( 'WP_CLI' ) || ! WP_CLI
	|| 'http://127.0.0.1:8100' !== untrailingslashit( get_option( 'home' ) ) || '1' !== getenv( 'COMMERCE_NATIVE_WOO_FIXTURE' ) ) {
	throw new RuntimeException( 'Use the disposable native Woo fixture only' );
}

wp_set_current_user( 1 );

if ( 'prepare' === $args[0] ) {
	foreach ( array( 'order.created', 'order.updated' ) as $topic ) {
		$webhook = new WC_Webhook();
		$webhook->set_name( 'Synthetic ' . $topic );
		$webhook->set_user_id( 1 );
		$webhook->set_topic( $topic );
		$webhook->set_api_version( 'wp_api_v3' );
		$webhook->set_secret( 'synthetic-native-woocommerce-webhook-secret' );
		$webhook->set_delivery_url( 'http://127.0.0.1:8100/webhooks/woocommerce/shop-test.danks.store' );
		$webhook->set_status( 'active' );
		$webhook->save();
	}
	exit;
}

if ( 'create' === $args[0] ) {
	$product = new WC_Product_Simple();
	$product->set_name( 'Synthetic webhook order product' );
	$product->set_sku( 'NATIVE-WOO-SYN' );
	$product->set_regular_price( '12.00' );
	$product->set_virtual( true );
	$product->save();

	$order = new WC_Order();
	$order->set_status( 'pending' );
	$order->set_currency( 'USD' );
	$order->add_product( $product, 1 );
	$order->set_billing_email( 'native-woo@example.invalid' );
	$order->set_billing_address_1( '1 Synthetic Street' );
	$order->calculate_totals();
	$order->save();
	echo wp_json_encode( array( 'id' => $order->get_id(), 'product' => $product->get_id() ) );
} elseif ( 'deliver' === $args[0] ) {
	$deliveries = array();
	add_action( 'woocommerce_webhook_delivery', function ( $http, $response ) use ( &$deliveries ) {
		$deliveries[] = array(
			'topic'  => $http['headers']['X-WC-Webhook-Topic'],
			'status' => wp_remote_retrieve_response_code( $response ),
			'error'  => is_wp_error( $response ) ? $response->get_error_code() : null,
		);
	}, 10, 2 );
	ActionScheduler_QueueRunner::instance()->run();
	echo wp_json_encode( $deliveries );
} elseif ( 'cancel' === $args[0] ) {
	$order = wc_get_order( (int) $args[1] );
	$order->update_status( 'cancelled' );
} else {
	throw new RuntimeException( 'Unknown fixture operation' );
}
