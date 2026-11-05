# Rooted Psyche Board supplementary libraries — issue #75

This is an opt-in extension to the existing Rooted Psyche Board Meeting Library. It keeps **Meeting Minutes unchanged** and adds separate protected sections for **Governance Documents**, **Treasury Reports** and **Working Documents**.

## Source of truth

```text
BookWorksSupplements/
  RootedPsycheBoard/
    Meeting Minutes/
      2026-10-01/
      2026-11-10/
    Governance Documents/
    Treasury Reports/
    working-documents.json  # generated from BookWorks, not manually edited
```

- Governance and treasury: curator copies approved board-visible *files only* into those direct folders. Do not recursively expose `BookWorksSources`, finances, counsel folders, signed/audit archives or unrelated files.
- Working Documents: source of truth is **BookWorks** `publications/rooted-psyche-corporate-record-book/chapters/11-board-editable-document-register.md`. A BookWorks export script generates the JSON derived from its eight Google Docs links and statuses. The WordPress plugin reads that file; it does not maintain duplicate URLs.
- Individual Google Docs sharing permissions must be reviewed and granted in Drive; the WordPress login does not confer access to Google Docs. The manifest's URL does not authorize anyone.
- Nothing automatically copies materials from sensitive archives. A reviewed copy in the curated folder means approved for distribution to the Board, not necessarily adopted or executed.

## Host provisioning (does not move/delete originals)

On Linode:

```bash
set -euo pipefail
ROOT='/mnt/GoogleDrive-ray@edanks.com/BookWorksSupplements/RootedPsycheBoard'
findmnt --target '/mnt/GoogleDrive-ray@edanks.com' -t fuse.rclone
mkdir -p "$ROOT/Governance Documents" "$ROOT/Treasury Reports"
ls -lah "$ROOT"
```

Add to private `~/RootedOps/.env` (keep the **existing** `ROOTEDPSYCHE_BOARD_MEETINGS_HOST_PATH` unchanged):

```dotenv
ROOTEDPSYCHE_BOARD_SUPPLEMENTS_HOST_PATH="/mnt/GoogleDrive-ray@edanks.com/BookWorksSupplements/RootedPsycheBoard"
```

Do not add raw source folders or the entire `BookWorksSources` as a WordPress mount.

## Deployment — after review/merge

Back up WordPress HTML+DB, merge the RootedOps PR, then `git pull --ff-only`. The **additional** Compose mount at `/srv/rootedpsyche-board-supplements` is read-only. Always supply both Compose files:

```bash
cd ~/RootedOps
sudo docker compose --env-file ./.env \
  -f docker/docker-compose.wordpress.yml \
  -f docker/docker-compose.rootedpsyche-board.yml config --quiet
sudo docker compose --env-file ./.env \
  -f docker/docker-compose.wordpress.yml \
  -f docker/docker-compose.rootedpsyche-board.yml up -d --no-deps rootedpsyche-wordpress
WP_CONTAINER="$(sudo docker compose --env-file ./.env \
  -f docker/docker-compose.wordpress.yml \
  -f docker/docker-compose.rootedpsyche-board.yml ps -q rootedpsyche-wordpress)"
test -n "$WP_CONTAINER"
sudo docker exec "$WP_CONTAINER" ls -lah /srv/rootedpsyche-board-supplements
```

**Copy the new helper before replacing the active main plugin** to prevent a momentary missing include:

```bash
sudo docker cp wordpress/plugins/rootedpsyche-board-library/board-sections.php \
  "$WP_CONTAINER":/var/www/html/wp-content/plugins/rootedpsyche-board-library/board-sections.php
sudo docker cp wordpress/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php \
  "$WP_CONTAINER":/var/www/html/wp-content/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php
sudo docker exec "$WP_CONTAINER" php -l /var/www/html/wp-content/plugins/rootedpsyche-board-library/board-sections.php
sudo docker exec "$WP_CONTAINER" php -l /var/www/html/wp-content/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php
```

Add three **separate Shortcode blocks** on the existing protected `/board/` page:

```text
[rootedpsyche_board_governance]
[rootedpsyche_board_treasury]
[rootedpsyche_board_working_documents]
```

Keep the existing `[rootedpsyche_board_meetings]` exactly as it is; no other WordPress pages are required.

## Single-source Working Documents export

The BookWorks PR adds a read-only exporter; on the MacBook with the BookWorks repository:

```bash
cd ~/GitHub/BookWorks
python3 shared/scripts/export_board_working_documents.py \
  --out /tmp/rooted-psyche-working-documents.json
```

This parses only the controlled Markdown table from chapter 11, validates the Google Docs links and emits an integrity/provenance record. After review, place this **generated** file into the supplements share under the exact filename `working-documents.json`. For example, if the Mac's Drive mount is available at `$DRIVE_MOUNT`:

```bash
DEST="$DRIVE_MOUNT/BookWorksSupplements/RootedPsycheBoard/working-documents.json"
test -d "$(dirname "$DEST")" && cp /tmp/rooted-psyche-working-documents.json "$DEST"
```

The Mac's `DRIVE_MOUNT` path must be set from its actual mounted Google Drive configuration; **do not assume that the Linode path exists on macOS**. Alternatively, transfer the generated JSON securely to the Linode and copy it into the mounted supplements root. Do not edit the JSON independently of BookWorks; re-export after changes to the register. WordPress reflects the new links on the next authorized refresh, without editing the portal page or rerunning a full BookWorks publication build.

## Tests / security gate

Before deployment:

```bash
php -l wordpress/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php
php -l wordpress/plugins/rootedpsyche-board-library/board-sections.php
php tests/test_rootedpsyche_board_library.php
php tests/test_rootedpsyche_board_sections.php
```

After deployment validate:
- Active Board Director and Administrator see the three sections; anonymous, Subscriber and revoked director do not.
- Direct governance and treasury URLs deny access without the director role, even when copied from an authorized account.
- Only flat PDF/DOCX/XLSX/ODT/ODS/TXT files up to 30 MiB in the two named folders are served; symlinks, traversal and other directories are denied.
- File addition/removal updates authorized lists without a BookWorks build. Working Docs follows the **exported** BookWorks manifest.
- Verify no public CDN/proxy caching or REST/search leakage of filenames/URLs; WordPress page protection alone is not enough.
- Check missing Drive mount causes unavailable message and no data leak. Verify plugin and DB recovery/rollback.

## Rollback

Remove the three new shortcodes from the Board Portal. Restore the previous plugin main file before removing `board-sections.php` (avoid a missing include), and roll back the optional mount using the earlier Compose version. Do not delete any Google Drive files.

Related: RootedOps #75, BookWorks #58.
