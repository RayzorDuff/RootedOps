<?php
get_header();
$shop = dank_storefront_woo_url( 'shop' );
$preview = dank_storefront_catalog_preview();
$featured_ids = array(
	711335074, 711335071, 711334876, 711335072, 711333863, 711335795,
	829845573, 711335797, 711335075, 828374466, 711334880, 711335076, 828374469, 711335798,
);
$featured = dank_storefront_products( $featured_ids, $preview );
?>
<main id="main-content">
	<section class="dank-hero" aria-labelledby="dank-hero-title">
		<img class="dank-hero-photo" src="<?php echo esc_url( get_theme_file_uri( 'assets/hero.webp' ) ); ?>" width="825" height="455" fetchpriority="high" alt="">
		<div class="dank-shell dank-hero-inner">
			<h1 id="dank-hero-title">Dank<br>Mushrooms</h1>
			<p>Fresh and freeze-dried gourmet mushrooms, grow kits, and mycology supplies from Johnstown, Colorado.</p>
			<a class="dank-button" href="<?php echo esc_url( $preview ? '#shop' : ( $shop ?: '#shop' ) ); ?>">Order now</a>
		</div>
	</section>

	<section class="dank-shell dank-featured" id="shop" aria-labelledby="dank-shop-title">
		<div class="dank-section-heading">
			<h2 id="dank-shop-title">Featured products</h2>
			<?php if ( $shop ) : ?><a class="dank-text-link" href="<?php echo esc_url( $shop ); ?>">Browse the shop <span aria-hidden="true">↗</span></a><?php endif; ?>
		</div>
		<?php dank_storefront_render_categories( $preview ); ?>
		<?php if ( $preview ) : ?><p class="dank-preview-note">Staging preview. Draft product cards are visible to store managers.</p><?php endif; ?>
		<?php if ( $featured ) :
			dank_storefront_render_products( $featured );
		else : ?>
			<p class="dank-empty">Gourmet mushrooms, grow kits, and supplies will appear here when the catalog is published.</p>
		<?php endif; ?>
	</section>

	<section class="dank-about" id="about" aria-labelledby="dank-about-title">
		<div class="dank-shell dank-split">
			<figure><img src="<?php echo esc_url( get_theme_file_uri( 'assets/about.webp' ) ); ?>" loading="lazy" width="850" height="637" alt="Pink oyster mushrooms growing from two cultivation blocks"></figure>
			<div>
				<h2 id="dank-about-title">About us</h2>
				<p>Dank Mushrooms grows gourmet mushrooms for home cooks and businesses. We offer fresh and freeze-dried mushrooms, plus the kits and supplies to grow your own.</p>
				<p>Try soaking freeze-dried gourmet mushrooms in water before cooking, or add ground freeze-dried reishi or lion’s mane to tea.</p>
			</div>
		</div>
	</section>

	<section class="dank-shell dank-delivery" id="delivery" aria-labelledby="dank-delivery-title">
		<h2 id="dank-delivery-title">Delivery &amp; returns</h2>
		<div class="dank-delivery-grid">
			<div><h3>Delivery</h3><p>Shipping options depend on the product and destination. Check your cart at checkout for the options available for your order.</p></div>
			<div><h3>Grow kits</h3><p>We guarantee the first harvest from grow kits and colonized substrate bags. Contact us with your order number if you need help.</p></div>
			<div><h3>Returns</h3><p>Most items can be returned within 15 days of delivery. Contact us with your order number and product details for return instructions.</p></div>
		</div>
	</section>

	<section class="dank-contact" id="contact" aria-labelledby="dank-contact-title">
		<div class="dank-shell dank-split">
			<div>
				<h2 id="dank-contact-title">Location &amp; contact</h2>
				<p>Based in Johnstown, Colorado. Contact us for current farmers market dates and help with your order.</p>
				<address>
					<a href="mailto:sales@danks.net">sales@danks.net</a><br>
					<a href="tel:+19705873294">970-587-3294</a>
				</address>
				<ul class="dank-social" aria-label="Social media"><li><a href="https://www.instagram.com/dankmushrooms/">Instagram</a></li><li><a href="https://www.facebook.com/dankmushroomsllc">Facebook</a></li><li><a href="https://www.youtube.com/@DankMushrooms">YouTube</a></li></ul>
				<p class="dank-directions"><a href="https://www.google.com/maps/dir/?api=1&amp;destination=1726+Goldenvue+Drive%2C+Johnstown%2C+CO+80534">Get directions <span aria-hidden="true">↗</span></a></p>
			</div>
			<figure><img src="<?php echo esc_url( get_theme_file_uri( 'assets/market.webp' ) ); ?>" loading="lazy" width="954" height="641" alt="Dank Mushrooms booth with a branded banner at an outdoor market"></figure>
		</div>
	</section>
</main>
<?php get_footer(); ?>
