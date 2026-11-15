<!doctype html>
<html <?php language_attributes(); ?>>
<head>
	<meta charset="<?php bloginfo( 'charset' ); ?>">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>
<a class="dank-skip" href="#main-content">Skip to content</a>
<header class="dank-header">
	<div class="dank-shell dank-header-inner">
		<a class="dank-brand" href="<?php echo esc_url( home_url( '/' ) ); ?>">
			<img src="<?php echo esc_url( get_theme_file_uri( 'assets/logo.png' ) ); ?>" alt="Dank Mushrooms" width="777" height="200">
		</a>
		<nav class="dank-nav" aria-label="Main navigation">
			<?php
			$shop = dank_storefront_woo_url( 'shop' );
			$account = dank_storefront_woo_url( 'myaccount' );
			$cart = dank_storefront_woo_url( 'cart' );
			if ( has_nav_menu( 'primary' ) ) :
				wp_nav_menu( array( 'theme_location' => 'primary', 'container' => false, 'depth' => 1 ) );
			else :
				?>
				<ul>
					<li><a href="<?php echo esc_url( $shop ?: home_url( '/#shop' ) ); ?>">Shop</a></li>
					<li><a href="<?php echo esc_url( home_url( '/#about' ) ); ?>">About</a></li>
					<li><a href="<?php echo esc_url( home_url( '/#delivery' ) ); ?>">Delivery</a></li>
					<li><a href="<?php echo esc_url( home_url( '/#contact' ) ); ?>">Contact</a></li>
				</ul>
			<?php endif; ?>
		</nav>
		<div class="dank-account">
			<?php if ( $account ) : ?><a href="<?php echo esc_url( $account ); ?>">My account</a><?php endif; ?>
			<?php if ( $cart ) : ?><a href="<?php echo esc_url( $cart ); ?>">Cart</a><?php endif; ?>
		</div>
	</div>
</header>
