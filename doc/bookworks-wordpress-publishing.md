# BookWorks → WordPress publication staging (v0)

This is a **generic, draft-only adapter**, not a fundraiser-specific content importer. BookWorks remains the authoritative manuscript and provenance system. RootedOps owns the WordPress adapter. No changes are made to the public website until an editor explicitly publishes the staged draft.

## Input contract

Create a UTF-8 JSON file with these fields:

```json
{
  "publication_id": "rooted-psyche-fundraising",
  "profile": "spiritual-center",
  "source_commit": "0123456789abcdef0123456789abcdef01234567",
  "title": "Rooted Psyche Spiritual Center Fund",
  "slug": "spiritual-center-fund",
  "html": "<h2>Draft heading</h2><p>Approved donor-facing text from BookWorks goes here.</p>"
}
```

The example commit is a placeholder, **not** a real publication revision. Use the full BookWorks Git SHA and validated, profile-specific donor-facing HTML. Do not include an entire HTML document with `html`, `head`, or `body` tags; the field is a content fragment. Do not use the BookWorks PDF or WordPress homepage as the source.

## Preview / stage

From the Linode after pulling RootedOps main:

```bash
bash scripts/import_bookworks_publication.sh /path/to/payload.json dry-run
bash scripts/import_bookworks_publication.sh /path/to/payload.json draft
```

The adapter checks the stable `publication_id:profile` key, refuses slug collisions, records the BookWorks source SHA and managed HTML hash, and refuses to overwrite manually changed WordPress content. It does not publish or add pages to navigation. Repeated identical imports are no-ops. Changed content moves the managed page back to draft for review.

## Limitations / next implementation steps

- The generic WordPress adapter is implemented, but the **BookWorks-side export** that assembles the JSON from validated profile-specific build output is not yet implemented. Do not fabricate fundraising copy or publish from placeholder JSON.
- Asset manifest/media synchronization and WordPress presentation ownership need separate implementation; inline image URLs are not automatically imported.
- WordPress may normalize markup on save. The next dry-run/update may detect such changes as a conflict; resolve by comparing the stored hash to the actual post body, not by forcibly overwriting.
- WordPress publication approvals, Givebutter campaign-specific links, and fundraising governance gates are separate from this adapter.
- Test in a staging WordPress instance before relying on the importer for live production drafts.

## WordPress environment and deployment configuration

The separate WordPress Compose stack reads these variables from the **local** RootedOps `.env` (sample values are maintained in `.env.example`):

```dotenv
ROOTEDPSYCHE_WP_DB_PASSWORD=change_me_unique_wordpress_db_password
ROOTEDPSYCHE_WP_DB_ROOT_PASSWORD=change_me_different_wordpress_root_password
ROOTEDPSYCHE_WP_TEST_PORT=8086
```

Use independently generated passwords, never sample values, and never commit real secrets. **Port 8086 also appears as `ERPNEXT_HTTP_PORT=8086` in the example**; when ERPNext is active, use `ROOTEDPSYCHE_WP_TEST_PORT=8096` (the WordPress Compose default and current production proxy upstream) or another verified free port. Do not change the production host port without reviewing the active Nginx configuration.

The current BookWorks release workflow uses immutable approved artifacts, checksum-verified native draft staging, read-only verification, and guarded native promotion/rollback commands in RootedOps. Fundraising widgets are owned by the RootedOps WordPress presentation plugin, outside BookWorks-managed `post_content`. Published-revision replacement remains a separate reviewed workflow; do not use draft staging to overwrite a published page. See `scripts/check_bookworks_native_release.sh` and `scripts/promote_bookworks_native.sh`. The earlier sections document the initial v0 importer and should not be treated as the complete current deployment contract.
