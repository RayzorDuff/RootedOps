# BookWorks fundraising WordPress presentation

This branch is intentionally separate from RootedOps main. It does not publish
pages or change the active WordPress theme.

## Draft import

The existing importer accepts the BookWorks `build-wordpress` JSON. It checks
the optional `html_sha256` against the original HTML, refuses nonempty media
manifests, sanitizes content through WordPress, and preserves manual-edit
protection and draft-only updates.

## Styling

`wordpress/bookworks-fundraising.css` contains scoped responsive styles for
`.bookworks-landing`, including the hero and budget table. This file is **not
automatically loaded** by WordPress. It must be reviewed and installed into
the active theme or an approved site-specific stylesheet/enqueue mechanism.
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
