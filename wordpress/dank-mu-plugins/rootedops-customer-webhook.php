<?php
/**
 * Plugin Name: RootedOps Customer Webhook
 * Description: Signals WooCommerce customer edits and guards ERP profile projection.
 */

defined( 'ABSPATH' ) || exit;

function rootedops_customer_sync_enabled() {
	return defined( 'ROOTEDOPS_CUSTOMER_WEBHOOK_ENABLED' ) && ROOTEDOPS_CUSTOMER_WEBHOOK_ENABLED;
}

function rootedops_customer_profile_fields( $scope ) {
	if ( 'account' === $scope || 'registered' === $scope ) {
		return array( 'email', 'first_name', 'last_name' );
	}
	$fields = array( 'address_1', 'address_2', 'city', 'state', 'postcode', 'country' );
	return 'billing' === $scope ? array_merge( $fields, array( 'phone' ) ) : $fields;
}

function rootedops_customer_profile_digest( $id, $scope ) {
	$customer = new WC_Customer( $id );
	$prefix   = in_array( $scope, array( 'account', 'registered' ), true ) ? '' : $scope . '_';
	$values   = array();
	foreach ( rootedops_customer_profile_fields( $scope ) as $field ) {
		$getter           = 'get_' . $prefix . $field;
		$values[ $field ] = trim( (string) $customer->$getter( 'edit' ) );
	}
	ksort( $values, SORT_STRING );
	return hash( 'sha256', wp_json_encode( $values, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_LINE_TERMINATORS ) );
}

function rootedops_customer_profile_signal( $id, $scope ) {
	if ( ! rootedops_customer_sync_enabled() ) {
		return;
	}
	$user = get_userdata( $id );
	if ( ! $user || ! in_array( 'customer', $user->roles, true ) ) {
		return;
	}
	do_action( 'woocommerce_rootedops_customer_profile_saved', array(
		'id'     => (int) $id,
		'scope'  => $scope,
		'event'  => wp_generate_uuid4(),
		'digest' => rootedops_customer_profile_digest( $id, $scope ),
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

/**
 * Serialize supported profile writers on the same Woo database connection.
 * Use a site-specific namespace, including for stores sharing a database server.
 */
function rootedops_customer_profile_lock( $id ) {
	global $wpdb;
	$key = hash( 'sha256', 'rootedops-customer-profile:' . DB_NAME . ':' . $wpdb->users . ':' . $id );
	if ( '1' !== (string) $wpdb->get_var( $wpdb->prepare( 'SELECT GET_LOCK(%s, 3)', $key ) ) ) {
		return null;
	}
	// Earlier request code may have loaded either user or user metadata before the lock.
	clean_user_cache( $id );
	wp_cache_delete( $id, 'user_meta' );
	return $key;
}

function rootedops_customer_profile_unlock( $key ) {
	global $wpdb;
	$wpdb->get_var( $wpdb->prepare( 'SELECT RELEASE_LOCK(%s)', $key ) );
}

function rootedops_customer_projection_enabled() {
	return rootedops_customer_sync_enabled() && in_array(
		wp_parse_url( home_url(), PHP_URL_HOST ),
		array( 'shop-test.danks.store', 'shop-test2.danks.store' ),
		true
	);
}

// Core fires these admin form hooks after the nonce and capability checks,
// but before it saves the profile. Observe profile_update only for this save.
function rootedops_prepare_admin_customer_profile_save( $id ) {
	if ( ! rootedops_customer_projection_enabled() || ! current_user_can( 'edit_user', $id ) ) {
		return;
	}
	$user = get_userdata( $id );
	if ( ! $user || ! in_array( 'customer', $user->roles, true ) ) {
		return;
	}

	$id  = (int) $id;
	$key = rootedops_customer_profile_lock( $id );
	if ( null === $key ) {
		wp_die( 'This customer account is being updated. Please try saving again.', '', array( 'response' => 503 ) );
	}
	add_action( 'shutdown', static function () use ( $key ) {
		rootedops_customer_profile_unlock( $key );
	}, PHP_INT_MAX );

	$before = rootedops_customer_profile_digest( $id, 'account' );
	add_action( 'profile_update', static function ( $updated_id ) use ( $id, $before ) {
		if ( $id === (int) $updated_id && $before !== rootedops_customer_profile_digest( $id, 'account' ) ) {
			rootedops_customer_profile_signal( $id, 'account' );
		}
	} );
}
add_action( 'edit_user_profile_update', 'rootedops_prepare_admin_customer_profile_save', 1 );
add_action( 'personal_options_update', 'rootedops_prepare_admin_customer_profile_save', 1 );

// Woo handles both forms on template_redirect at priority 10.
add_action( 'template_redirect', function () {
	if ( ! rootedops_customer_projection_enabled() ) {
		return;
	}
	$actions = array(
		'save_account_details' => array( 'save-account-details-nonce', 'save_account_details' ),
		'edit_address'         => array( 'woocommerce-edit-address-nonce', 'woocommerce-edit_address' ),
	);
	$action = $_POST['action'] ?? '';
	if ( ! is_string( $action ) || ! isset( $actions[ $action ] ) ) {
		return;
	}
	list( $field, $nonce_action ) = $actions[ $action ];
	$nonce = $_REQUEST[ $field ] ?? $_REQUEST['_wpnonce'] ?? '';
	$id    = get_current_user_id();
	if ( ! $id || ! is_string( $nonce ) || ! wp_verify_nonce( $nonce, $nonce_action ) ) {
		return;
	}
	$key = rootedops_customer_profile_lock( $id );
	if ( null === $key ) {
		wp_die( 'Your account is being updated. Please try saving again.', '', array( 'response' => 503 ) );
	}
	add_action( 'shutdown', static function () use ( $key ) {
		rootedops_customer_profile_unlock( $key );
	}, PHP_INT_MAX );
}, 5 );

add_action( 'rest_api_init', function () {
	if ( ! rootedops_customer_projection_enabled() ) {
		return;
	}
	// The wc namespace uses WooCommerce REST authentication and key permissions.
	register_rest_route( 'wc/v3', '/customers/(?P<id>[1-9][0-9]*)/rootedops-projection', array(
		'methods'             => 'PUT',
		'permission_callback' => static function ( $request ) {
			return function_exists( 'wc_rest_check_user_permissions' )
				&& wc_rest_check_user_permissions( 'edit', (int) $request->get_url_params()['id'] );
		},
		'callback'            => 'rootedops_customer_project_profile',
	) );
} );

function rootedops_customer_project_profile( $request ) {
	$input  = $request->get_json_params();
	$scope  = $input['scope'] ?? null;
	$digest = $input['expected_digest'] ?? null;
	$values = $input['values'] ?? null;
	if ( ! in_array( $scope, array( 'account', 'billing', 'shipping' ), true )
		|| ! is_string( $digest ) || ! preg_match( '/\A[0-9a-f]{64}\z/', $digest ) || ! is_array( $values ) ) {
		return new WP_Error( 'rootedops_projection_shape', 'Invalid profile projection.', array( 'status' => 400 ) );
	}
	$fields = rootedops_customer_profile_fields( $scope );
	if ( count( $values ) !== count( $fields ) || array_diff_key( array_flip( $fields ), $values )
		|| count( array_filter( $values, 'is_string' ) ) !== count( $values ) ) {
		return new WP_Error( 'rootedops_projection_fields', 'Invalid profile projection fields.', array( 'status' => 400 ) );
	}

	$id  = (int) $request->get_url_params()['id'];
	$key = rootedops_customer_profile_lock( $id );
	if ( null === $key ) {
		return new WP_Error( 'rootedops_profile_busy', 'Customer profile is busy.', array( 'status' => 503 ) );
	}
	try {
		$user = get_userdata( $id );
		if ( ! $user || ! in_array( 'customer', $user->roles, true ) ) {
			return new WP_Error( 'rootedops_projection_customer', 'Woo customer unavailable.', array( 'status' => 404 ) );
		}
		if ( ! hash_equals( $digest, rootedops_customer_profile_digest( $id, $scope ) ) ) {
			return new WP_Error( 'rootedops_profile_changed', 'Woo profile changed before projection.', array( 'status' => 412 ) );
		}
		$update = new WP_REST_Request( 'PUT', '/wc/v3/customers/' . $id );
		$update->set_body_params( 'account' === $scope ? $values : array( $scope => $values ) );
		return rest_do_request( $update );
	} finally {
		rootedops_customer_profile_unlock( $key );
	}
}
