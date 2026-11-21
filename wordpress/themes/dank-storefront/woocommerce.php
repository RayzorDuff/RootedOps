<?php get_header(); ?>
<main class="dank-shell dank-page" id="main-content">
	<?php if ( is_shop() || is_product_category() ) : ?>
		<div class="dank-shop-categories"><?php dank_storefront_render_categories(); ?></div>
	<?php endif; ?>
	<?php woocommerce_content(); ?>
</main>
<?php get_footer(); ?>
