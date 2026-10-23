# BookWorks fundraising WordPress presentation

RootedOps develops this integration on main. Installation does not publish
pages or change the active WordPress theme.

## Draft import

The existing importer accepts the BookWorks `build-wordpress` JSON. It checks
the optional `html_sha256` against the original HTML, refuses nonempty media
manifests, sanitizes content through WordPress, and preserves manual-edit
protection and draft-only updates.

## Styling

`wordpress/bookworks-fundraising.css` contains scoped responsive styles for
`.bookworks-landing`, including the hero and budget table. The MU plugin `wordpress/bookworks-fundraising-loader.php` loads the stylesheet
only for pages whose BookWorks publication key begins with
`rooted-psyche-fundraising:`. Install both files using:

```bash
cd ~/RootedOps
git pull --ff-only origin main
bash scripts/install_bookworks_fundraising_styles.sh
```

This copies files into the running container. Confirm that your WordPress
`wp-content` volume persists across container replacement; otherwise install
these files in the persistent volume or repeat the installation after recreation.
Do not paste this stylesheet into publication content.

## Media

The current BookWorks publication figure registry is empty. Do not invent a
hero image or point at a local image path. A later change should define an
approved media manifest, stage verified image bytes, upload them idempotently
to the Media Library, and rewrite references only after successful upload.

## Deployment safeguards

Run the importer in `dry-run` mode before `draft`. Review page 15 in the
WordPress preview. Do not publish, modify the homepage, or modify global
navigation/footer settings as part of this integration.
