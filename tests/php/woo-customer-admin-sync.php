<?php

define( 'ABSPATH', __DIR__ );
define( 'DB_NAME', 'example' );
define( 'ROOTEDOPS_CUSTOMER_WEBHOOK_ENABLED', true );

$hooks = array();
$events = array();
$first_name = 'Before';
$allow_edit = true;
$wpdb = new class {
	public $users = 'wp_users';
	public $locks = 0;
	public function prepare( $query, $key ) { return $query; }
	public function get_var( $query ) {
		$this->locks += str_contains( $query, 'GET_LOCK' ) ? 1 : -1;
		return 1;
	}
};

class WC_Customer {
	public function __construct( $id ) {}
	public function get_first_name( $context ) { return $GLOBALS['first_name']; }
	public function get_last_name( $context ) { return 'Example'; }
	public function get_email( $context ) { return 'fixture@example.invalid'; }
}

function add_action( $name, $callback, $priority = 10, $accepted_args = 1 ) {
	$GLOBALS['hooks'][ $name ][ $priority ][] = array( $callback, $accepted_args );
}

function do_action( $name, ...$args ) {
	$handlers = $GLOBALS['hooks'][ $name ] ?? array();
	ksort( $handlers );
	foreach ( $handlers as $group ) {
		foreach ( $group as list( $callback, $accepted_args ) ) {
			$callback( ...array_slice( $args, 0, $accepted_args ) );
		}
	}
}

function current_user_can( $capability, $id ) { return $GLOBALS['allow_edit']; }
function get_userdata( $id ) { return (object) array( 'roles' => array( $id === 3 ? 'customer' : 'editor' ) ); }
function home_url() { return $GLOBALS['fixture_origin'] ?? 'https://shop-test.danks.store'; }
function wp_parse_url( $url, $component ) { return parse_url( $url, $component ); }
function wp_generate_uuid4() { return 'ed219744-fa90-4a23-90e5-45c8dfd74543'; }
function wp_json_encode( $value, $flags ) { return json_encode( $value, $flags ); }
function clean_user_cache( $id ) {}
function wp_cache_delete( $id, $group ) {}

function expect( $condition, $message ) {
	if ( ! $condition ) {
		throw new RuntimeException( $message );
	}
}

function end_fixture_request() {
	do_action( 'shutdown' );
	unset( $GLOBALS['hooks']['shutdown'], $GLOBALS['hooks']['profile_update'] );
}

require __DIR__ . '/../../wordpress/dank-mu-plugins/rootedops-customer-webhook.php';
add_action( 'woocommerce_rootedops_customer_profile_saved', static function ( $event ) {
	$GLOBALS['events'][] = $event;
} );

do_action( 'edit_user_profile_update', 3 );
expect( $wpdb->locks === 1, 'Admin save should hold the projection lock' );
$first_name = 'After';
do_action( 'profile_update', 4 );
expect( count( $events ) === 0, 'Updates to other users must not emit' );
do_action( 'profile_update', 3 );
expect( count( $events ) === 1 && $events[0]['scope'] === 'account' && $events[0]['id'] === 3,
	'Admin save must emit the updated customer profile' );
expect( $events[0]['digest'] === rootedops_customer_profile_digest( 3, 'account' ), 'Digest must reflect saved fields' );
end_fixture_request();
expect( $wpdb->locks === 0, 'Shutdown should release the profile lock' );

do_action( 'personal_options_update', 3 );
do_action( 'profile_update', 3 );
end_fixture_request();
expect( count( $events ) === 1, 'Unchanged account fields must not emit' );

$first_name = 'Projection';
do_action( 'profile_update', 3 );
expect( count( $events ) === 1, 'A programmatic update outside the form must not emit' );

do_action( 'edit_user_profile_update', 4 );
$allow_edit = false;
do_action( 'edit_user_profile_update', 3 );
expect( $wpdb->locks === 0, 'Noncustomers and unauthorized edits must not take the sync lock' );
$fixture_origin = 'https://dankmushrooms.net';
$allow_edit = true;
do_action( 'edit_user_profile_update', 3 );
$first_name = 'New hostname';
do_action( 'profile_update', 3 );
end_fixture_request();
expect( count( $events ) === 2, 'Canonical hostname must emit existing customer edits' );
$fixture_origin = 'https://unreviewed.invalid';
expect( !rootedops_customer_projection_enabled(), 'Unknown hostname must remain disabled' );
echo "Woo admin customer sync checks passed.\n";
