<?php
/**
 * Plugin Name: BookWorks Original HTML Renderer
 * Description: Displays approved, same-origin BookWorks HTML inside a WordPress page without reformatting the publication.
 * Version: 0.1.0
 */
if (!defined('ABSPATH')) exit;

add_shortcode('bookworks_publication', function ($atts) {
    $atts = shortcode_atts(['file' => ''], $atts, 'bookworks_publication');
    $file = $atts['file'];
    // Fixed public directory and HTML filenames only; no arbitrary URL or filesystem paths.
    if (!preg_match('/^[a-z0-9][a-z0-9-]*\.html$/', $file)) return '';
    $url = home_url('/bookworks/' . $file);
    $id = 'bookworks-' . substr(hash('sha256', $file), 0, 12);
    ob_start();
    ?>
    <div class="bookworks-publication-frame" style="width:100%;max-width:100%;margin:0 auto">
      <iframe id="<?php echo esc_attr($id); ?>" title="<?php echo esc_attr(get_the_title() ?: 'BookWorks publication'); ?>"
        src="<?php echo esc_url($url); ?>" loading="eager"
        style="display:block;width:100%;min-height:85vh;border:0;overflow:hidden"
        scrolling="no"></iframe>
    </div>
    <script>
    (function(){
      const frame = document.getElementById(<?php echo wp_json_encode($id); ?>);
      if (!frame) return;
      let observer;
      function resize() {
        try {
          const doc = frame.contentDocument;
          if (!doc) return;
          const height = Math.max(doc.documentElement.scrollHeight, doc.body ? doc.body.scrollHeight : 0);
          if (height > 0) frame.style.height = (height + 8) + 'px';
        } catch (e) { frame.style.overflow = 'auto'; frame.setAttribute('scrolling','auto'); }
      }
      frame.addEventListener('load', function(){
        if (observer) observer.disconnect();
        resize();
        try {
          const doc = frame.contentDocument;
          if (doc && window.ResizeObserver) {
            observer = new ResizeObserver(resize);
            observer.observe(doc.documentElement);
            if (doc.body) observer.observe(doc.body);
          }
          if (doc && doc.fonts && doc.fonts.ready) doc.fonts.ready.then(resize);
          if (doc) {
            doc.querySelectorAll('img').forEach(img => img.addEventListener('load', resize));
            doc.addEventListener('click', function(event){
              const a = event.target.closest('a[href^="#"]');
              if (!a) return;
              // Keep the publication's own chapter navigation; do not alter its HTML.
              setTimeout(resize, 0);
            });
          }
        } catch(e) {}
      });
      window.addEventListener('resize', resize);
    })();
    </script>
    <?php
    return ob_get_clean();
});

// The BookWorks HTML already contains its own cover/title. Suppress only the
// WordPress theme's Post Title block on managed original-HTML pages.
add_filter('render_block', function ($content, $block) {
    if (($block['blockName'] ?? '') !== 'core/post-title' || is_admin() || !is_singular('page')) return $content;
    $page_id = get_queried_object_id();
    if (!$page_id || !get_post_meta($page_id, '_bookworks_original_key', true)) return $content;
    return '';
}, 10, 2);
