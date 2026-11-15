<?php
/**
 * Plugin Name: RootedOps Customer Webhook
 * Description: Signals explicitly saved WooCommerce account fields to the commerce inbox.
 */

defined( 'ABSPATH' ) || exit;

function rootedops_customer_profile_signal( $id, $scope ) {
	if ( ! defined( 'ROOTEDOPS_CUSTOMER_WEBHOOK_ENABLED' ) || ! ROOTEDOPS_CUSTOMER_WEBHOOK_ENABLED ) {
		return;
	}
	$user = get_userdata( $id );
	if ( ! $user || ! in_array( 'customer', $user->roles, true ) ) {
		return;
	}

	$customer = new WC_Customer( $id );
	if ( 'account' === $scope || 'registered' === $scope ) {
		$values = array( 'email' => $customer->get_email( 'edit' ), 'first_name' => $customer->get_first_name( 'edit' ), 'last_name' => $customer->get_last_name( 'edit' ) );
	} else {
		$values = array_intersect_key( $customer->{"get_$scope"}( 'edit' ), array_flip( array( 'address_1', 'address_2', 'city', 'state', 'postcode', 'country' ) ) );
		if ( 'billing' === $scope ) {
			$values['phone'] = $customer->get_billing_phone( 'edit' );
		}
	}
	$values = array_map( 'trim', $values );
	ksort( $values, SORT_STRING );
	do_action( 'rootedops_customer_profile_saved', array(
		'id'       => (int) $id,
		'scope'    => $scope,
		'event'    => wp_generate_uuid4(),
		'digest'   => hash( 'sha256', wp_json_encode( $values, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_LINE_TERMINATORS ) ),
	) );
}

add_action( 'woocommerce_created_customer', function ( $id ) {
	rootedops_customer_profile_signal( $id, 'registered' );
} );
add_action( 'woocommerce_save_account_details', function ( $id ) {
	rootedops_customer_profile_signal( $id, 'account' );
} );
add_action( 'woocommerce_customer_save_address', function ( $id, $type ) {
	if ( get_current_user_id() === (int) $id && in_array( $type, array( 'billing', 'shipping' ), true ) ) {
		rootedops_customer_profile_signal( $id, $type );
	}
}, 10, 2 );
