<footer class="dank-footer">
	<div class="dank-shell dank-footer-inner">
		<a class="dank-brand" href="<?php echo esc_url( home_url( '/' ) ); ?>">
			<img src="<?php echo esc_url( get_theme_file_uri( 'assets/logo.png' ) ); ?>" alt="Dank Mushrooms" width="777" height="200" loading="lazy">
		</a>
		<p>Johnstown, Colorado</p>
		<ul>
			<li><a href="<?php echo esc_url( home_url( '/#delivery' ) ); ?>">Delivery &amp; returns</a></li>
			<li><a href="<?php echo esc_url( home_url( '/#contact' ) ); ?>">Contact</a></li>
			<?php if ( get_privacy_policy_url() ) : ?><li><a href="<?php echo esc_url( get_privacy_policy_url() ); ?>">Privacy</a></li><?php endif; ?>
		</ul>
	</div>
</footer>
<?php wp_footer(); ?>
</body>
</html>
