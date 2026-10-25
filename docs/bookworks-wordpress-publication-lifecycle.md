# BookWorks original-HTML WordPress lifecycle

## Source of truth and safety

BookWorks builds the public-introduction profile and creates a checksum-approved `wordpress-original-html` release in BookWorksArtifacts. RootedOps deploys it. WordPress pages are stable pointers containing `[bookworks_publication file="<slug>.html"]`; they are **not** recreated on every revision.

- `deploy_bookworks_original_html.sh --mode check`: validate approved release, no WordPress change.
- `deploy_bookworks_original_html.sh --mode stage`: **draft-only**, initial publication. Does not publish.
- `promote_bookworks_original_html.sh --mode check`: validate approved release and published WordPress page, shortcode, slug, management-key ownership.
- `promote_bookworks_original_html.sh --mode promote`: adopt an exact existing published shortcode page if necessary, archive current HTML by SHA-256, replace file atomically, record checksum and promotion time.
- `promote_bookworks_original_html.sh --mode rollback --to-sha <sha256>`: restore a previously archived HTML blob by its **exact checksum** after validating its archived bytes. No WordPress page deletion/recreation.

**Limitations:** The rollback archive preserves prior HTML bytes, not a separately re-approved release; the operator must select a known previous hash from deployment output. The existing approved release is still required for identity/preflight, but the rollback target is identified by checksum. The deployment does not alter page status, title, navigation, or URL. The PHP helper enforces exact shortcode matching. The script assumes one deployment operator at a time; serialize promotions externally.

## Existing Spiritual Foundations page (ID 41)

Page 41 was published manually after staging. Keep it published and do not recreate it. The first `promote` will adopt it by setting `_bookworks_original_key` if that metadata is missing, but only if its slug and shortcode match and no other page owns the key. Use `check` first.

On the Mac, run `make wordpress-approve-book BOOK=publications/rooted-psyche-spiritual-foundations PROFILE=public-introduction SLUG=spiritual-foundations STYLE=original-html`. Record the revision printed in the approved release. On the Linux RootedOps server, locate the corresponding absolute directory under `/mnt/GoogleDrive-ray@edanks.com/BookWorksArtifacts/rooted-psyche-spiritual-foundations/wordpress-original-html/public-introduction/<revision>`.

```bash
cd ~/RootedOps
git pull --ff-only origin main
RELEASE="/mnt/GoogleDrive-ray@edanks.com/BookWorksArtifacts/rooted-psyche-spiritual-foundations/wordpress-original-html/public-introduction/<revision>"
bash scripts/promote_bookworks_original_html.sh --release "$RELEASE" --mode check
# Only when an updated publication has been reviewed and approved:
bash scripts/promote_bookworks_original_html.sh --release "$RELEASE" --mode promote
```

If a previous version needs restoration, use the checksum printed as `previous=<sha256>`:

```bash
bash scripts/promote_bookworks_original_html.sh --release "$RELEASE" --mode rollback --to-sha "<previous-sha256>"
```

## First publication of Spiritual Mission and Community Served

1. In BookWorks, validate/build the `public-introduction` profile and inspect all five illustrations in PDF/DOCX/HTML.
2. Coordinate public copy, fund references, and release timing with the **Spiritual Recovery and Access Fund**. Do not publish an unready fund link.
3. Approve a WordPress original-HTML release using `make wordpress-approve-book` with:
   - `BOOK=publications/rooted-psyche-spiritual-mission-and-community-served`
   - `PROFILE=public-introduction`
   - `SLUG=spiritual-mission-and-community-served`
   - `STYLE=original-html`
4. On the RootedOps server, run `deploy_bookworks_original_html.sh --release <absolute-release-directory> --mode check`, then `--mode stage`.
5. Activate the BookWorks renderer plugin if not already active. Run the existing `stage_bookworks_original_html.php KEY SLUG check` then `stage` in the WordPress container. This creates a **draft** page. Review it and publish using WordPress admin when the companion fund is ready.
6. For subsequent approved revisions of the published page, use `promote_bookworks_original_html.sh --mode check` then `--mode promote`. Do not stage a published page or trash/recreate it.

## Operational verification checklist

- Verify WordPress page ID, published status, and exact shortcode before and after.
- Verify current live HTML checksum matches the expected promoted hash.
- Verify the public permalink and the page-ID URL, chapter images, navigation, and responsive presentation.
- Test rollback against a nonproduction WordPress container before relying on it in production.
- Keep deployment logs, previous SHA-256, and BookWorks approval receipts together for audit.

## Fail-closed cases

Reject invalid or mismatched approval receipts; changed HTML; mismatched source revision; wrong slug or shortcode; a page not published for promotion; duplicate managed keys; an existing page owned by another key; missing backup or checksum mismatch; and a rollback target that is not present in the content-addressed archive.
