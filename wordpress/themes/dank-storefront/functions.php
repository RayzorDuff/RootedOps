<?php
/** Set up the Dank Mushrooms storefront. */

defined( 'ABSPATH' ) || exit;

add_action( 'after_setup_theme', function () {
	add_theme_support( 'title-tag' );
	add_theme_support( 'post-thumbnails' );
	add_theme_support( 'woocommerce' );
	add_theme_support( 'wc-product-gallery-zoom' );
	add_theme_support( 'wc-product-gallery-lightbox' );
	add_theme_support( 'wc-product-gallery-slider' );
	add_theme_support( 'html5', array( 'search-form', 'comment-form', 'comment-list', 'gallery', 'caption', 'style', 'script' ) );
	register_nav_menus( array( 'primary' => 'Storefront navigation' ) );
} );

add_action( 'wp_enqueue_scripts', function () {
	wp_enqueue_style( 'dank-storefront', get_stylesheet_uri(), array(), wp_get_theme()->get( 'Version' ) );
} );

function dank_storefront_woo_url( $page ) {
	if ( ! function_exists( 'wc_get_page_id' ) || wc_get_page_id( $page ) < 1 ) {
		return '';
	}
	return get_permalink( wc_get_page_id( $page ) ) ?: '';
}

function dank_storefront_catalog_preview() {
	return isset( $_GET['dank_catalog_preview'] )
		&& '1' === $_GET['dank_catalog_preview']
		&& 'shop-test.danks.store' === wp_parse_url( home_url(), PHP_URL_HOST )
		&& current_user_can( 'manage_woocommerce' );
}

add_action( 'template_redirect', function () {
	if ( dank_storefront_catalog_preview() ) {
		nocache_headers();
	}
} );

function dank_storefront_products( $source_ids, $preview ) {
	if ( ! function_exists( 'wc_get_product' ) ) {
		return array();
	}
	$keys = array_map( static function ( $id ) {
		return 'ecwid:95802503:product:' . $id;
	}, $source_ids );
	$posts = get_posts( array(
		'post_type'              => 'product',
		'post_status'            => $preview ? array( 'publish', 'draft' ) : 'publish',
		'meta_key'               => '_rootedops_source_key',
		'meta_value'             => $keys,
		'meta_compare'           => 'IN',
		'posts_per_page'         => -1,
		'update_post_term_cache' => true,
	) );
	$products_by_key = array();
	foreach ( $posts as $post ) {
		$key = get_post_meta( $post->ID, '_rootedops_source_key', true );
		$products_by_key[ $key ][] = $post->ID;
	}
	$products = array();
	foreach ( $keys as $key ) {
		if ( 1 !== count( $products_by_key[ $key ] ?? array() ) ) {
			continue;
		}
		$id = $products_by_key[ $key ][0];
		$product = wc_get_product( $id );
		if ( ! $product ) {
			continue;
		}
		$public = 'publish' === $product->get_status()
			&& in_array( $product->get_catalog_visibility(), array( 'visible', 'catalog' ), true )
			&& $product->is_visible();
		$previewable = $preview && current_user_can( 'edit_post', $id );
		if ( $public || $previewable ) {
			$products[] = array( 'product' => $product, 'public' => $public );
		}
	}
	return $products;
}

function dank_storefront_render_products( $products ) {
	if ( ! $products ) {
		return;
	}
	?>
	<ul class="dank-product-grid">
		<?php foreach ( $products as $entry ) :
			$product = $entry['product'];
			$url = $entry['public'] ? $product->get_permalink() : '';
			$description = wp_trim_words( wp_strip_all_tags( $product->get_short_description() ), 19 );
			?>
			<li class="dank-product">
				<?php if ( $url ) : ?><a class="dank-product-link" href="<?php echo esc_url( $url ); ?>"><?php endif; ?>
				<div class="dank-product-image">
					<?php echo wp_kses_post( $product->get_image( 'woocommerce_thumbnail', array( 'loading' => 'lazy' ) ) ); ?>
				</div>
				<div class="dank-product-text">
					<h3><?php echo esc_html( $product->get_name() ); ?></h3>
					<?php if ( $description ) : ?><p><?php echo esc_html( $description ); ?></p><?php endif; ?>
					<div class="dank-product-meta">
						<?php echo wp_kses_post( $product->get_price_html() ); ?>
						<?php if ( ! $entry['public'] ) : ?><span class="dank-status">Staging preview</span>
						<?php elseif ( ! $product->is_in_stock() ) : ?><span class="dank-status">Sold out</span><?php endif; ?>
					</div>
				</div>
				<?php if ( $url ) : ?></a><?php endif; ?>
			</li>
		<?php endforeach; ?>
	</ul>
	<?php
}

function dank_storefront_render_categories( $preview = false ) {
	if ( ! taxonomy_exists( 'product_cat' ) ) {
		return;
	}
	$categories = get_terms( array(
		'taxonomy' => 'product_cat',
		'hide_empty' => ! $preview,
		'parent' => 0,
		'exclude' => array( (int) get_option( 'default_product_cat' ) ),
	) );
	if ( is_wp_error( $categories ) || ! $categories ) {
		return;
	}
	?>
	<ul class="dank-categories" aria-label="Product categories">
		<?php foreach ( $categories as $category ) :
			$url = get_term_link( $category );
			if ( ! is_wp_error( $url ) ) : ?>
				<li><a href="<?php echo esc_url( $url ); ?>"><?php echo esc_html( $category->name ); ?></a></li>
			<?php endif;
		endforeach; ?>
	</ul>
	<?php
}

add_action( 'template_redirect', function () {
	if ( ! is_404() || ! function_exists( 'wc_get_product' )
		|| ! in_array( $_SERVER['REQUEST_METHOD'] ?? '', array( 'GET', 'HEAD' ), true ) ) {
		return;
	}
	$path = wp_parse_url( wp_unslash( $_SERVER['REQUEST_URI'] ?? '' ), PHP_URL_PATH );
	if ( ! is_string( $path ) ) {
		return;
	}
	$path = untrailingslashit( $path );
	$legacy_pages = array( '/products' => 'shop', '/products/account' => 'myaccount', '/products/cart' => 'cart' );
	$legacy_categories = array(
		'160254004' => 'gourmet-mushrooms',
		'160255005' => 'miscellaneous',
		'160277251' => 'grow-kits-and-mycology-supplies',
	);
	$target = '';
	if ( isset( $legacy_pages[ $path ] ) ) {
		$target = dank_storefront_woo_url( $legacy_pages[ $path ] );
	} elseif ( preg_match( '#^/products/[^/]+-p([0-9]{1,16})$#D', $path, $match ) ) {
		$products = dank_storefront_products( array( $match[1] ), false );
		if ( 1 === count( $products ) ) {
			$target = $products[0]['product']->get_permalink();
		}
	} elseif ( preg_match( '#^/products/[^/]+-c([0-9]{1,16})$#D', $path, $match )
		&& isset( $legacy_categories[ $match[1] ] ) ) {
		$term = get_term_by( 'slug', $legacy_categories[ $match[1] ], 'product_cat' );
		if ( $term && $term->count > 0 ) {
			$link = get_term_link( $term );
			$target = is_wp_error( $link ) ? '' : $link;
		}
	}
	if ( $target && $path !== untrailingslashit( (string) wp_parse_url( $target, PHP_URL_PATH ) )
		&& wp_safe_redirect( $target, 302, 'Dank Storefront' ) ) {
		exit;
	}
}, 9 );
