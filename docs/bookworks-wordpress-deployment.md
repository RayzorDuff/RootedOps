# BookWorks → WordPress deployment (phase 1)

This is the supported entry point for **schema v1, media-free** BookWorks WordPress JSON packages. It replaces separate presentation-install and importer commands. It does **not** build BookWorks sources, upload media, change WordPress navigation, or publish anything.

On the BookWorks Mac, build a public-facing profile with `make build-wordpress`, then transfer the generated JSON to the RootedOps server using the existing approved transport. The builder requires a clean tracked Git working tree and embeds its source commit and HTML checksum.

On Linode:

```bash
cd ~/RootedOps
git pull --ff-only origin main
bash scripts/deploy_bookworks_publication.sh \
  --payload /tmp/spiritual-center-wordpress.json \
  --expected-key rooted-psyche-fundraising:spiritual-center \
  --mode check
```

`check` validates the JSON locally, then asks WordPress for a **read-only** plan. It does not install assets or change content.

For a **new or existing draft**, use `--mode stage` only after reviewing the plan. This installs the current presentation files, stages the draft, and checks idempotency. The importer refuses unexpected edits and refuses to change a published page to a draft. A published page with matching content returns `unchanged`.

**Important:** The existing Spiritual Center Fund is already published. Do not run `stage` to update it; published-page revisions need a separate review and release path. `check` remains safe.

## Next phases (not implemented yet)

- Portable media manifest: role, path, SHA-256, MIME, alt text, caption, conceptual-vs-documentary disclosure; transport from BookWorksSources/BookWorksArtifacts without depending on GitHub Actions having Mac files.
- Idempotent WordPress Media Library upload and attachment-role association, including strict `photo`/`concept` roles and no silent defaults.
- Generic WordPress layout adapter for public-facing book editions, separate from the current fundraising-specific presentation.
- Versioned published-page revision workflow with explicit approval, preview, conflict detection, and rollback.
- Automated PHP and shell integration tests in CI against a disposable WordPress instance.
- Eventually an end-to-end Mac build/package/transfer command. No unattended publication.


## Phase 2: explicit media packaging (initial implementation)

BookWorks `shared/scripts/package_wordpress_media.py` packages approved images from a JSON plan into an independent directory containing `manifest.json` and `assets/`. The plan identifies `publication_key` and each image's `role`, absolute or home-relative `source`, `alt`, `caption`, and optional expected `sha256`. Only JPEG, PNG, and WebP files are accepted. Example plan:

```json
{
  "publication_key": "rooted-psyche-fundraising:spiritual-center",
  "assets": [
    {
      "role": "photo",
      "source": "/path/to/approved/actual-site-photo.jpg",
      "sha256": "REPLACE_WITH_ACTUAL_64_CHARACTER_SHA256",
      "alt": "Actual mountain landscape at the proposed sanctuary",
      "caption": "Existing sanctuary landscape near Livermore, Colorado."
    },
    {
      "role": "concept",
      "source": "/path/to/approved/concept.png",
      "sha256": "REPLACE_WITH_ACTUAL_64_CHARACTER_SHA256",
      "alt": "Concept illustration of proposed sanctuary improvements",
      "caption": "Concept illustration only. Proposed sanctuary improvements are illustrative; the finished design may change as plans are developed."
    }
  ]
}
```

Build on Mac: `python3 shared/scripts/package_wordpress_media.py --plan /path/to/plan.json --out /tmp/bookworks-media-package`. Transfer the **whole package directory** to Linode, e.g. `scp -r /tmp/bookworks-media-package dankmushrooms@appsmith.danks.store:/tmp/`.

On Linode:

```bash
bash scripts/sync_bookworks_media.sh /tmp/bookworks-media-package/manifest.json /tmp/bookworks-media-package/assets check
# For a reviewed DRAFT only:
bash scripts/sync_bookworks_media.sh /tmp/bookworks-media-package/manifest.json /tmp/bookworks-media-package/assets stage
```

`check` verifies files and WordPress managed-page identity without writing. `stage` only accepts an existing **draft** page, imports/deduplicates by SHA-256, and saves an explicit role→attachment map in `_bookworks_media_roles`. It never changes managed `post_content` or page status. A published page is **not eligible** for staging. This intentionally protects the already-published Spiritual Center Fund; do not run `stage` against page 15.

**Current limitation:** the generic role map is not yet consumed by the fundraising presentation adapter, which still uses its historical attachment metadata. The importer and wrapper need disposable-WordPress integration tests and lint before production use. Do not mistake the package command for a complete automatic rendering/deployment pipeline.
