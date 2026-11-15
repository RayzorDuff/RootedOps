# Board Portal v0.3 — nested governance, separate resolutions and protected BookWorks publication

## Source-of-truth / directory contract

```text
BookWorksSupplements/RootedPsycheBoard/
  Meeting Minutes/YYYY-MM-DD/  # Meeting notes, attendance, agenda, meeting packets
  Board Resolutions/            # Authoritative signed Board actions (optional YYYY/ subfolders)
  Governance Documents/
    Colorado/                   # SOS filings, Articles and accepted amendments
    IRS/                        # determination letter and federal filings approved for Board distribution
    Policies/                   # currently adopted Bylaws, conflict policy, etc.
  Treasury Reports/
  working-documents.json        # BookWorks-derived; do not manually edit
```

Only place final Board-visible copies in these explicitly curated folders. **Do not mirror the whole source archive or automatically expose tax returns, confidential IRS attachments, counsel material, personal identifiers or financial account details**. The Board's access does not turn a document into an adopted record.

Existing `[rootedpsyche_board_meetings]` remains unchanged. Existing governance shortcode now traverses curated subfolders (up to 8 levels), excluding links, hidden files, unsupported extensions, and oversized files. New resolutions shortcode `[rootedpsyche_board_resolutions]` uses a completely separate allowlisted folder; each download checks `board_director` or `administrator`. `[rootedpsyche_board_treasury]` and `[rootedpsyche_board_working_documents]` are unchanged.

**No duplicate signed resolution PDFs:** Move/curate copies into `Board Resolutions/` *after checking completeness*, and preserve originals in the historical source. Meeting Minutes can keep the minutes and reference the resolution register but should not repeat the signed PDF. Never call an unsigned record signed.

## Approved BookWorks Board Readiness HTML publication

BookWorks build for the existing `rooted-psyche-corporate-record-book:board-readiness` profile, followed by an **approved versioned release** to `BookWorksArtifacts/`, not hand-editing the WordPress page or staging an arbitrary JSON:

On Mac:
```bash
cd ~/GitHub/BookWorks
git switch main && git pull --ff-only origin main
make validate-governance
make build-book BOOK=publications/rooted-psyche-corporate-record-book
make wordpress-approve-book BOOK=publications/rooted-psyche-corporate-record-book PROFILE=board-readiness SLUG=board-readiness
```
The final command creates `BookWorksArtifacts/rooted-psyche-corporate-record-book/wordpress/board-readiness/<source-commit>/` with `deploy.sh`, `wordpress.json`, receipts and an empty media manifest. **No sensitive content is uploaded through the Media Library.**

On Linode (after RootedOps PR merged, Git pull, backup, and verifying shared Google Drive mount):
```bash
cd ~/RootedOps
git pull --ff-only origin main
RELEASE="/mnt/GoogleDrive-ray@edanks.com/BookWorksArtifacts/rooted-psyche-corporate-record-book/wordpress/board-readiness/<source-commit>"
test -f "$RELEASE/deploy.sh"
bash "$RELEASE/deploy.sh" check
bash "$RELEASE/deploy.sh" stage
# Inspect check result, WordPress page ID, parent and role metadata; make backup,
# ensure no REST/search/cache leak and compare approved content before promotion.
bash "$RELEASE/deploy.sh" promote
```

**Protected target only:** Existing published `/board/board-readiness/`, under `/board/`. No new page and no publishing to the top-level slug. The dedicated RootedOps importer rejects unexpected page identity, unrecognized roles or missing Members plugin; it requires explicit Board Director restrictions at least on the parent, and checks the child (if configured). `check` and `stage` are nonmutating dry runs. `promote` updates only the existing page body, preserves parent/title/status/Members metadata and records a checksum-addressable rollback snapshot. Rollback is `bash "$RELEASE/deploy.sh" rollback <previous-sha256>`.

**Security acceptance required before running promote:** First verify Members content permissions settings, direct access denial by anonymous/subscriber and revoked director, and no REST/search/cache exposure. The Members plugin restricts *content*, not necessarily page titles, metadata or media; therefore never publish sensitive attachments through the Media Library.

## Persistent Board mounts and recovery

The default Rooted Psyche WordPress Compose service now always includes `/srv/rootedpsyche-board-meetings` and `/srv/rootedpsyche-board-supplements` as read-only mounts. On the Linode, confirm the Google Drive mount is healthy before starting/recreating WordPress, then use `sudo docker compose --env-file ./.env -f docker/docker-compose.wordpress.yml config --quiet` and `sudo docker compose --env-file ./.env -f docker/docker-compose.wordpress.yml up -d --no-deps rootedpsyche-wordpress`. An existing `.env` with the two correct paths needs no changes. Do not overwrite the private `.env` from `.env.example`.

The WordPress **Working Documents** shortcode reads `BookWorksSupplements/RootedPsycheBoard/working-documents.json`. **New approved BookWorks Board Readiness releases now include a checksummed snapshot** of the chapter 11 links. The release's `check`/`stage` validate the manifest and the live mount without writing, and `promote` updates the protected WordPress page and then installs the manifest in the Google Drive supplements root. The previous manifest is retained under a digest-specific `working-documents.before-*.json` name. Older releases without a manifest remain deployable and do not change the current links. Board WordPress rollback remains page-only; if rolling back a release that changed links, restore the intended manifest separately from the saved backup. Validate BookWorks and RootedOps release helpers before production promotion. A complete release must be built from merged BookWorks main.

### Board Working Documents release checks

On the Mac, run `make wordpress-approve-book BOOK=publications/rooted-psyche-corporate-record-book PROFILE=board-readiness SLUG=board-readiness`. Inspect the resulting release folder for `working-documents.json` and `approval.json` containing `working_documents_sha256` and `working_documents_count`.

On Linode, run `python3 -m unittest discover -s tests -p 'test_board_working_documents_publish.py'` from RootedOps, and then the existing `bash "$RELEASE/deploy.sh" check`, `stage`, `promote` sequence. The deployment helper uses the actual WordPress container read-only bind source to identify the Google Drive host directory and refuses to write if the source is not on `fuse.rclone`. After promote, verify the nine working links and source commit from the mounted manifest.

## Deploy plugin upgrade

Use existing `ROOTEDPSYCHE_BOARD_MEETINGS_HOST_PATH` and `ROOTEDPSYCHE_BOARD_SUPPLEMENTS_HOST_PATH` from the private `.env`. As of the permanent-mount fix, **both read-only binds live in `docker/docker-compose.wordpress.yml`**; the old `docker-compose.rootedpsyche-board.yml` remains a harmless compatibility overlay. Use the primary WordPress Compose file for future recreations. Never run with `--remove-orphans`.

After PR review/merge:
```bash
cd ~/RootedOps
git pull --ff-only origin main
php -l wordpress/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php
php -l wordpress/plugins/rootedpsyche-board-library/board-hierarchy.php
php tests/test_rootedpsyche_board_library.php
php tests/test_rootedpsyche_board_sections.php
php tests/test_rootedpsyche_board_hierarchy.php
WP_CONTAINER=docker-rootedpsyche-wordpress-1
sudo docker cp wordpress/plugins/rootedpsyche-board-library/board-hierarchy.php \
  "$WP_CONTAINER":/var/www/html/wp-content/plugins/rootedpsyche-board-library/board-hierarchy.php
sudo docker cp wordpress/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php \
  "$WP_CONTAINER":/var/www/html/wp-content/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php
```

Existing shortcode remains `[rootedpsyche_board_governance]`. Add a separate WordPress Shortcode block containing `[rootedpsyche_board_resolutions]` to `/board/`. Do not create the folder as world-readable host static web assets.

## Audit checklist

- [ ] All file access is role checked; unknown section tokens, nested traversal, symlinks and unsupported extensions rejected.
- [ ] Anonymous/subscriber/revoked director fails direct file access as well as shortcode listing; check REST, search, cache.
- [ ] Colorado and IRS nested folders render correctly, with subfolder labels.
- [ ] Board Resolutions distinct from Meeting Minutes, no duplicates.
- [ ] Verify filed/adopted/executed status against originals; only curate intended Board-accessible files.
- [ ] WordPress Board Readiness `check` identifies protected existing child page and refuses unexpected roles/hierarchy.
- [ ] Approved release, checksum and WordPress backup verified before `promote`.
- [ ] Post-promotion role/security tests and rollback check pass.

Related RootedOps #75 and BookWorks Corporate Record Book.
