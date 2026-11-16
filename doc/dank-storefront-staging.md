# Dank Mushrooms WordPress storefront

The theme in `wordpress/themes/dank-storefront` moves the live Ecwid home
presentation onto `shop-test.danks.store`. It reuses the store's logo, mushroom
photos and market photo. Copy is condensed and the undated market announcement
is replaced with the current contact path. Keep delivery and returns copy in
step with final Woo shipping policy before launch.

The homepage reads the original featured selection from WooCommerce using exact
Ecwid product provenance. Product images, names, prices and stock come from Woo.
The shop, product categories, cart, checkout and account pages use the existing
Woo configuration. The theme does not change product publication or visibility,
inventory, payments, tax, accounts, WordPress options, or Woo settings.

## Install on the staging Woo site

1. Verify the URL in WordPress Admin and take the existing staging backup.
2. Build the ZIP from a checkout containing this change.

   ```bash
   cd ~/RootedOps/wordpress/themes
   zip -r /tmp/dank-storefront.zip dank-storefront
   ```

3. In **Appearance → Themes**, note the active theme. Choose **Add Theme →
   Upload Theme**, install the ZIP and activate **Dank Storefront**. The
   source ZIP must contain a single top-level `dank-storefront` directory.
4. While signed in with Woo management access, open
   `https://shop-test.danks.store/?dank_catalog_preview=1`. Only this exact
   staging host and users with edit access may see draft product cards.
   Draft cards have no product or purchase link. In a signed-out window,
   confirm they remain absent even when that query parameter is included.
5. Test the homepage at desktop and mobile widths. Check the logo and local
   images, the Shop and Contact navigation, Woo Shop and category listings,
   and one authorized product preview. View Cart and My Account without
   placing an order. Compare the navigation and photos with `danks.store`.
   The staging Woo Store API already lists three migrated categories. They
   become public navigation links once they contain published products.
6. Roll back the presentation by reactivating the previously active theme.
   No catalog rebuild or database restore is needed for theme rollback.

## Legacy links

The source sitemap exposed 38 product URLs and three public category URLs.
The theme handles unresolved Ecwid product URLs such as
`/products/Turkey-Tail-Liquid-Culture-Syringe-p711335074` using the numeric
source ID and only one published, catalog-visible Woo product. It also maps
the three Ecwid category IDs to the migrated Woo category slugs and maps the
old shop, account and cart paths to the existing Woo pages. It returns a
temporary redirect to the local canonical destination when a match is ready.
Hidden, excluded, ambiguous, or missing products keep their normal 404.
Existing WordPress routes take precedence. Requests to `qr.danks.store`
remain part of the separate QR cutover and should be checked against the
resulting product URLs.

Before cutover, sample the product and category URLs in the Ecwid sitemap,
verify old paths reach the correct Woo pages, review the two source utility
paths (`/qa` and `/hidden-disabled`), and make a separate decision on
permanent redirects once the destination catalog is published. Keep the
live Ecwid storefront available through staging review and checkout acceptance.
