<?php get_header(); ?>
<main class="dank-shell dank-page" id="main-content">
	<?php if ( is_404() ) : ?>
		<h1>Page not found</h1>
		<p><a href="<?php echo esc_url( home_url( '/' ) ); ?>">Return to Dank Mushrooms</a></p>
	<?php elseif ( have_posts() ) : ?>
		<?php if ( is_archive() ) : the_archive_title( '<h1>', '</h1>' ); endif; ?>
		<?php while ( have_posts() ) : the_post(); ?>
			<article <?php post_class(); ?>>
				<?php if ( is_singular() ) : ?>
					<h1><?php the_title(); ?></h1>
					<?php the_content(); wp_link_pages(); ?>
				<?php else : ?>
					<h2><a href="<?php the_permalink(); ?>"><?php the_title(); ?></a></h2>
					<?php the_excerpt(); ?>
				<?php endif; ?>
			</article>
		<?php endwhile; ?>
		<?php the_posts_pagination(); ?>
	<?php else : ?>
		<h1>No results found</h1>
		<?php get_search_form(); ?>
	<?php endif; ?>
</main>
<?php get_footer(); ?>
