# Rooted Psyche Board meeting library (issue #75)

**Status:** opt-in implementation in PR; do **not** expose private files until security tests pass.

## Architecture
- Members `board_director` WordPress role or `administrator` controls authorization.
- The `rootedpsyche-board-library` WordPress plugin supplies shortcode `[rootedpsyche_board_meetings]` and a role-gated same-site download endpoint.
- Only immediate files inside date directories matching `YYYY-MM-DD` are eligible, with extensions PDF, DOCX, XLSX, ODT, ODS or TXT and a 30 MiB limit. Nested folders, links, and unsupported files are **excluded**.
- The approved Google Drive directory is mounted by rclone on **the host**, then injected read-only into the WordPress container through an **opt-in Compose override** at `/srv/rootedpsyche-board-meetings`.
- The rclone Google Drive share must be shared with named secretary/directors as appropriate. Sharing in Drive and WordPress roles are independent.
- No files are copied to public WordPress Media Library. A browser cannot access the host mount path directly. Never add an Nginx alias to the drive.
- The filename is displayed only to logged-in directors/admins. Every download rechecks roles and file identity. Downloads use attachment disposition, no-store headers, and no MIME sniffing.
- Directory content is discovered on each authorized page request; **no BookWorks build** is needed when a secretary adds a file. Reload page to refresh.
- Approved records should separately be frozen/versioned in BookWorks; files in this live folder are working board materials, not automatically adopted records.

## Host hierarchy
Use the operator-created **BookWorksSupplements/RootedPsycheBoard** root, alongside `BookWorksSources` and `BookWorksArtifacts`. This is an operational supplement reusable by other BookWorks publications, not the immutable BookWorks source catalog:

```text
/mnt/GoogleDrive-ray@edanks.com/BookWorksSupplements/RootedPsycheBoard/
  Meeting Minutes/
    2026-10-01/
    2026-11-10/
```

This is a **BookWorks operational supplements hierarchy**, not a BookWorks source dump. The existing folder named `DankMushrooms/Rooted Psyche/Legal Framework/Meeting Minutes` is the historical *input*; do not serve that entire tree. The root is created on the mounted Google Drive only by the operator. The secretary may be given edit access to the Meeting Minutes directory in Google Drive, while the WordPress container receives read-only access. Avoid allowing broadly shared source trees to become board downloadable.

## Provisioning completed by operator (November 4/5, 2026)
The operator already verified the `gdrive2:` mount and created `2026-10-01` and `2026-11-10`. These commands are idempotent verification/recovery steps, **not new work required**:

```bash
set -euo pipefail
MOUNT='/mnt/GoogleDrive-ray@edanks.com'
ROOT="$MOUNT/BookWorksSupplements/RootedPsycheBoard/Meeting Minutes"
findmnt --target "$MOUNT" -t fuse.rclone
mkdir -p "$ROOT/2026-10-01" "$ROOT/2026-11-10"
ls -ld "$ROOT" "$ROOT"/20*
```

Before sharing, check Drive permissions: granting editing access to a folder may allow its editor to delete or move files. Keep approved signed originals under separate restricted archival custody.

### Copy the known October 1 board-facing PDF files
Operator inventory from November 4 identified these immediate source PDFs:
- `01-Initial-Interim-Board-Resolution.pdf`
- `02-Initial-Board-Conflict-Disclosure-and-Assessment.pdf`
- `03-Bank-Account-Authorization-Resolution.pdf`
- `05-Governance-Document-Conformity-Resolution.pdf`
- `Interim Board Meeting Minutes _ 20261001.pdf`

The operator already copied these five PDFs into the new `BookWorksSupplements` location (reported total approximately 849 KiB). The copy commands below are retained for disaster recovery; all preserve the source and do not overwrite existing target files. The presence of a file in this library does **not** confirm that it has been adopted or legally executed; verify status separately.

```bash
set -euo pipefail
MOUNT='/mnt/GoogleDrive-ray@edanks.com'
SRC="$MOUNT/DankMushrooms/Rooted Psyche/Legal Framework/Meeting Minutes/October 1, 2026"
DST="$MOUNT/BookWorksSupplements/RootedPsycheBoard/Meeting Minutes/2026-10-01"
for name in \
  '01-Initial-Interim-Board-Resolution.pdf' \
  '02-Initial-Board-Conflict-Disclosure-and-Assessment.pdf' \
  '03-Bank-Account-Authorization-Resolution.pdf' \
  '05-Governance-Document-Conformity-Resolution.pdf' \
  'Interim Board Meeting Minutes _ 20261001.pdf'
do
  test -f "$SRC/$name" || { echo "Missing source: $name" >&2; exit 1; }
  if test -e "$DST/$name"; then
    echo "Already exists, skipped: $name"
  else
    cp -p -- "$SRC/$name" "$DST/$name"
    echo "Copied: $name"
  fi
done
ls -lah "$DST"
```

Do not bulk-copy the nested `Rooted-Psyche-Initial-Board-Meeting-Packet 3` folder, counsel review, DOCX drafts, or `Signed` folder. The user can curate and copy specific approved signed records later (the plugin intentionally does not recurse). For example, first verify what is signed and appropriate, then use `cp -n -- "$SRC/Signed/<exact-file>.pdf" "$DST/"`. Duplicate draft/final filenames should be renamed to a clear reviewed name *in the destination*, never overwrite an original.

The `2026-11-10` folder has been created and was initially empty. The secretary can add notes, reports, and meeting packet files as they become available. New files become visible after a page refresh with no BookWorks build.

## Deploy after PR review
**Do not deploy automatically.** Confirm a recent WordPress backup and restore procedure. Make sure the rclone mount is active and the new directory exists. Preserve the existing WordPress Compose file and TLS config.

1. Add to the private `~/RootedOps/.env` (do not put secrets into Git):
   ```dotenv
   ROOTEDPSYCHE_BOARD_MEETINGS_HOST_PATH=/mnt/GoogleDrive-ray@edanks.com/BookWorksSupplements/RootedPsycheBoard/Meeting Minutes
   ```
2. After merging and pulling, validate combined Compose:
   ```bash
   cd ~/RootedOps
   sudo docker compose --env-file ./.env \
     -f docker/docker-compose.wordpress.yml \
     -f docker/docker-compose.rootedpsyche-board.yml config --quiet
   sudo docker compose --env-file ./.env \
     -f docker/docker-compose.wordpress.yml \
     -f docker/docker-compose.rootedpsyche-board.yml up -d --no-deps rootedpsyche-wordpress
   ```
   This recreates the WordPress container to add one read-only bind mount. WordPress's persistent volume, DB, and unrelated containers remain unchanged; verify before running in production. Future Compose operations for this service must include **both** files to retain the mount.
3. Locate the actual container id through `docker compose ... ps -q rootedpsyche-wordpress`. Install the single plugin file in `wp-content/plugins/rootedpsyche-board-library/` (its files persist in the existing WordPress HTML volume):
   ```bash
   WP_CONTAINER="$(sudo docker compose --env-file ./.env \
     -f docker/docker-compose.wordpress.yml \
     -f docker/docker-compose.rootedpsyche-board.yml ps -q rootedpsyche-wordpress)"
   test -n "$WP_CONTAINER"
   sudo docker exec "$WP_CONTAINER" mkdir -p /var/www/html/wp-content/plugins/rootedpsyche-board-library
   sudo docker cp wordpress/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php \
     "$WP_CONTAINER":/var/www/html/wp-content/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php
   sudo docker exec "$WP_CONTAINER" php -l /var/www/html/wp-content/plugins/rootedpsyche-board-library/rootedpsyche-board-library.php
   sudo docker exec "$WP_CONTAINER" ls -lah /srv/rootedpsyche-board-meetings
   ```
4. In WordPress admin **Plugins**, activate **Rooted Psyche Board Meeting Library**.
5. In the existing Members-protected `/board/` page, add a **Shortcode** block containing `[rootedpsyche_board_meetings]`. Remove any public meeting list/navigation item. No separate meeting WordPress pages required.
6. Validate as board director, anonymous visitor, ordinary subscriber, removed director, and administrator. Try a guessed/captured download link in an unauthenticated session: must fail (403). Ensure no public caching, search or REST listing exposure.

## Critical tests before adding sensitive documents
- Allowed board director sees only `2026-10-01` and `2026-11-10` and only approved leaf files, with file links that download.
- Anonymous/subscriber/revoked role cannot list files through shortcode or download even with a captured full URL.
- Add a harmless test PDF to `2026-11-10`, refresh authorized page; it appears with no build or WordPress edit. Remove it; it disappears.
- Simulate missing mount in test; no leaks/errors to user, downloads blocked.
- Test malformed base64/unknown date/file, symlink, nested directory, extension rejected, >30 MiB file rejected.
- Validate no CDN/proxy HTML caching for `/board/`, any page with shortcode, or `rp_board_download` URLs; `Cache-Control: private, no-store` on downloads.
- Do not use Google-native Docs as if ordinary downloadable PDFs: decide to use PDF/DOCX exports or explicitly permissioned Google Docs links. No automatic Google Drive API authorization.
- Test backup/restore for plugin and mount configuration; plugin files are in WordPress persistent HTML volume.
- If a folder is accessible through another Google shared-link mechanism, its Drive ACL may grant access independently; review sharing rules.

## Rollback
Remove the shortcode, deactivate the plugin, and bring WordPress up with the baseline Compose file (removing the read-only mount). Do not delete Google Drive files. Preserve and inspect backups before cleanup. All code changes require PR review.
