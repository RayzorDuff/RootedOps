# BookWorks original HTML renderer (prototype)

This WordPress plugin displays the **original, unchanged** BookWorks HTML in a same-origin iframe, retaining the active WordPress theme's header and footer. It does **not** import publication content into WordPress blocks, rewrite image sizes, or modify the theme.

## Trial with the existing file

1. Install the directory `wordpress/plugins/bookworks-original-html` as `wp-content/plugins/bookworks-original-html` and activate **BookWorks Original HTML Renderer** in WordPress.
2. Confirm the already-uploaded HTML is available at `/bookworks/rooted-psyche-spiritual-foundations-public-introduction.html`.
3. Create a **draft** WordPress page containing only this Shortcode block:

   `[bookworks_publication file="rooted-psyche-spiritual-foundations-public-introduction.html"]`

4. Preview the page. The plugin preserves the standalone document's CSS and embedded images. It resizes the iframe on document, image, and font load and on responsive changes.
5. Compare the standalone HTML and preview at desktop and mobile sizes. Do not remove the existing published page until the replacement is accepted.

## Important boundaries

- This prototype does **not** yet modify `deploy_bookworks_artifact.sh` or change the approval/checksum mechanism. A follow-up integration must stage the *approved original HTML* and any relative assets to the `/bookworks/` directory, then register the shortcode page as a draft. Never silently publish or overwrite a live page.
- WordPress header/footer and the BookWorks document are separate HTML documents. Internal chapter links work inside the iframe, but browser URL fragments/back navigation to individual chapters require additional testing.
- The iframe is same-origin; if the site's Content-Security-Policy or `X-Frame-Options` prohibits same-origin framing, adjust the site configuration only after reviewing its security implications.
- The shortcode intentionally accepts a simple HTML basename only. It does not accept remote URLs or arbitrary filesystem paths.
- Only deploy reviewed/approved BookWorks HTML: same-origin framing allows script in the embedded document to interact with the parent page. Keep public uploads under a controlled, non-executable static HTML directory.
- The shortcode doesn't alter WordPress menus, page status, or existing publication pages.

## Next integration

Extend the approved BookWorksArtifacts release format to carry the original HTML and relative assets with SHA-256 digests. Update RootedOps deployment to verify those digests, install static assets atomically, and create/update only an unpublished WordPress shortcode page. Keep the current importer available for the fundraising page and other existing consumers.

## New original-HTML deployment command (development branch)

`scripts/deploy_bookworks_original_html.sh` is an **opt-in** parallel path. It does not replace the existing WordPress JSON importer.

**Approval prerequisite:** A separate `original-html-approval.json` must bind the exact standalone HTML digest to the existing approved `approval.json` receipt. Do not edit the existing approval receipt. Prepare the sidecar using `python3 scripts/approve_bookworks_original_html.py --release "$RELEASE" --html "$APPROVED_HTML"` (pending review), then after comparing the publication and confirming approval, create it with `--approve` instead. The script refuses to overwrite a prior sidecar; remove a pending review sidecar only after checking it. The deployment script fails closed if the sidecar is missing, pending, or inconsistent.

```bash
cd ~/RootedOps
bash scripts/deploy_bookworks_original_html.sh --release "$RELEASE" --html "$APPROVED_HTML" --mode check
bash scripts/deploy_bookworks_original_html.sh --release "$RELEASE" --html "$APPROVED_HTML" --mode stage
```

The stage command copies the plugin and HTML into the existing WordPress container, checks the transferred HTML checksum, and prints the exact CLI commands to create a draft. **Plugin activation is intentionally manual** and must precede draft creation.

The original HTML must currently be self-contained (e.g. embedded images) or use assets already accessible at the correct relative URLs. Packaging and verifying a complete external asset manifest is a remaining requirement before generalizing this to all publications.

**Not yet completed:** generalized asset-bundle handling, WordPress server execution, preview testing, and publication. This separate approval step is intentionally explicit; it does not claim to represent a preexisting BookWorksArtifacts approval. This branch must not be represented as deployed to production.
