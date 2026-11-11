# Nightly full-stack recovery bundle

The November 10 restore rehearsal exposed a producer/consumer defect: the nightly
job saved image names but not custom runtime images, omitted the independently
deployed Dank WordPress site and both LibreChat installations, and had no
completeness inventory. The full restorer could silently omit missing archives.
Passing SHA256SUMS proved only that the files present had not changed.

ERPNext images can also declare an anonymous child volume at
`/home/frappe/frappe-bench/sites/assets`, even when Compose declares only the
parent `sites` volume. This child is inventoried separately when actually mounted:
each distinct child is saved once as `volumes/erpnext_assets_NN.tgz`, with the
original shared/distinct consumer topology and read-only mount settings preserved.
Recovery creates new project-local named child volumes and restores their bytes
after the parent. It neither skips the child nor assumes the parent archive
contains it. Hosts without that child need no additional assets archive. Only
exact known Frappe public-asset symlinks may escape an assets archive into the
restored apps volume; other escaping links remain rejected.

The inventory failure occurs before image export, SQL dumps or application pause.
After merging the correction, rerun the same image plan and normal backup commands.
No volume removal, bootstrap rerun or crontab change is required for this failure.

The repaired **existing nightly job** produces a new, complete timestamp directory.
Do not supplement the old `20261110-231728` snapshot with separately exported
images. Keep that set unchanged as historical evidence and use a fresh snapshot
for the next attempt. No production backup or restore is executed by this commit.

## What the nightly job now captures

- `meta/recovery-bundle.json`: format version, explicit installed/not-installed
  groups, actual source container/mount identities, immutable image IDs and every
  required recovery payload. Raw container environments are never serialized.
- Published runtime images use **anonymously verified immutable registry digests**
  and the recorded platform. Their image bytes are omitted. This includes services
  configured with floating tags: the snapshot records their exact deployed digest,
  never whatever `latest` points to at restore time. Loaded public images missing
  RepoDigests can use a matching digest resolved from their original tags.
- `images/runtime-images.tar.gz` is optional and contains **only local/custom images
  with no verified published source**, deduplicated by used image ID. Locally built
  Documenso and ERPNext are expected candidates; a published matching image is
  pulled instead whenever verified. Unused/candidate images are never selected.
  Production image tags are never modified. A registry-only snapshot has no image
  archive at all.
- Existing five PostgreSQL logical dumps, ERPNext and Rooted Psyche MariaDB
  dumps, and the installed Dank WordPress MariaDB dump/content volume.
- Both installed LibreChat MongoDB clusters and data/uploads/log volumes,
  consistent cold Appsmith/n8n volumes, ERP apps/sites, and scheduling clusters.
  Empty LibreChat uploads/data/log directories and Redis caches are legitimate;
  empty MongoDB/Appsmith/n8n/scheduling databases are rejected.
- Actual bind mounts, including Board documents, LibreChat configuration and
  Rallly Garage configuration. These remain private backup payloads. Source
  mounts outside the inventory fail instead of being silently discarded.
- Original local recovery keys in private `meta/.env` and Rallly's private env
  archive. Do not delete them or paste their contents into chat/GitHub.

Only genuinely uninstalled optional groups can be recorded as not installed.
Partial groups, duplicate service candidates and orphaned known persistent
volumes cause failure. The installed image/container/mount inventory is checked
again around the snapshot so a concurrent redeployment cannot silently mix image
and data generations. The legacy Minecraft archive remains separate and is not
started by the full-stack test restorer. Documenso's browser cache is disposable.

## Production execution after owner review and merge

Use the **same deployment Unix account, production checkout and rclone config as
the existing cron job**. Do not replace the private `.env` or install test defaults
on production. From that checkout:

```bash
git status --short
# Continue only with a clean production deployment checkout.
git pull --ff-only origin main
bash -n backup/backup-stack.sh backup/volume-tools.sh
umask 077
install -d -m 700 "$HOME/.local/state"
SKIP_BACKUP_PRUNE=true bash backup/backup-stack.sh \
  > "$HOME/.local/state/rootedops-recovery-backup.log" 2>&1
tail -n 20 "$HOME/.local/state/rootedops-recovery-backup.log"
```

The success line identifies the new timestamp and remote directory. No cron
change is needed: future runs invoke the same script. Run this manual backup in
a quiet window. All managed application writers are stopped while logical SQL
and persistent files are captured; logical PostgreSQL/MariaDB servers stay up.
Embedded/raw MongoDB, scheduling and Redis containers are stopped too. Previously
stopped services remain stopped. An EXIT handler retries restarting the exact
containers stopped by this run, including after a failed dump/archive. A failed
restart prevents successful publication. Unexpected power loss/SIGKILL still
requires operator recovery; no shell EXIT handler can guarantee recovery then.
External clients writing directly to databases must also be quiesced by the
operator. Do not deploy/change containers while the backup runs.

Registry verification and any necessary custom-image export precede the application
pause. Timeouts, rate limits, transient errors or mismatching registry content fail
the job **before** pausing applications; they never silently archive every public
image during an outage. An explicit registry response that an image is unpublished
or not publicly accessible classifies it for archival. A local RepoDigest alone
is not proof of publication: Docker 29 can assign one to an unpushed build. Restore needs registry/network availability for those pinned
public images; registry retirement or removal will block recovery, not trigger an
unreviewed upgrade. The operator can decide how to preserve a retired image if
that occurs.

The private log and inventory report every selected image, recovery method, reason,
source services and uncompressed size. The summary records registry bytes omitted,
custom image counts/bytes and actual compressed archive bytes. Image sizes are
Docker's reported sizes; shared layers can make the compressed export smaller than
the sum. Only unavoidable custom-image bytes increase snapshot storage. Layers are
deduplicated within their one export, not across nightly remote snapshots. The
existing retention policy is unchanged; this first manual run disables pruning.
A single local lock prevents cron/manual overlap.

To review the exact image selection without pausing applications, exporting images,
dumping databases or uploading a snapshot, run from the production checkout:

```bash
BACKUP_IMAGE_PLAN_ONLY=true bash backup/backup-stack.sh
```

This performs read-only local inventory and anonymous registry verification and
prints the selection/size report. It is not a backup or a successful recovery
receipt. Use the normal job afterward to create the fresh complete snapshot.

The producer checks its complete inventory and image archive before upload.
Remote verification must pass before retention. A failed job never prints a
successful completion line. Review failures in the protected log; do not publish
its contents or payloads. Credentials and Board/participant records remain private.

## Transfer one complete fresh snapshot

Copy the entire new timestamp directory to `~/backups/` on the new test Linode,
using the same existing Mac/Drive/rsync method. Include `images/`, `meta/.env`,
`meta/recovery-bundle.json`, all dumps/archives and the original `SHA256SUMS`.
Do not merge snapshots or regenerate their manifest. Inside the new directory:

```bash
sha256sum --check SHA256SUMS
```

The initial new Linode remains suitable because no restored containers or volumes
were created. Downloaded images alone do not count as a partial data restore.
Do not rerun bootstrap over its existing generated credentials. If any restore
has created a `RESTORE_STARTED` marker or populated volumes, use a separately
reviewed fresh target rather than removing the marker or overwriting data.

## Restore from the bundle

Use the new snapshot path in place of `NEW_TIMESTAMP`:

```bash
cd ~/RootedOps
git pull --ff-only origin main
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" \
  "$HOME/backups/NEW_TIMESTAMP" --prepare-images
sudo python3 scripts/host_recovery.py validate "$PWD/.test-deployment"
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" \
  "$HOME/backups/NEW_TIMESTAMP" --source-site erp.danks.store --check-only
sudo python3 scripts/full_restore.py "$PWD/.test-deployment" \
  "$HOME/backups/NEW_TIMESTAMP" --source-site erp.danks.store
```

Preparation pulls the recorded public digests/platforms, loads only the necessary
archived custom images, verifies every exact local identity and pins only the
already isolated generated Compose files. It never starts services,
builds floating application refs or copies production networking/port settings.
The image receipt binds this snapshot inventory to those Compose files. Full
restore refuses missing payloads, missing image preparation, changed images or
changed Compose configuration. Explicit subset recovery retains its historical
scope and cannot be presented as complete recovery.

Runtime bind content is restored privately under `.test-deployment/` and mounted
there instead of accessing original host/external mount paths. Source signing
material remains quarantined; the test Documenso certificate/passphrase are
retained. Restored configurations, credentials stored inside apps and callbacks
still require the isolation review before any application starts. Neither data
restoration nor image preparation permits public exposure or live automation.

See [fresh-host-recovery.md](fresh-host-recovery.md) for stopped application,
workflow/datasource isolation, service checks, reboot and round-trip acceptance.
The post-v1.2.0 SignatureGate backup is the baseline; do not replay release
migrations just because the host is new. This repair makes the next rehearsal
possible; it does not claim that the full production recovery acceptance passed.

## Validation and rollback

Regression coverage includes mixed public/custom and registry-only nightly
snapshots, source-image/platform matching, missing-digest public-tag recovery,
unused image exclusion, no export or pause during a registry outage, the read-only
image plan, SQL/volume completeness, exact image pinning, source identity drift,
previously stopped apps, failure-path restarts and no-upload-on-failure. CI exercises
native pinned-registry pull plus custom-image save/gzip/load and the existing
stopped-volume recovery fixture. Full production backup/recovery awaits
the owner-generated fresh snapshot and the subsequent isolated acceptance run.

To roll back code, revert this change through review, leaving existing snapshots
and generated test credentials intact. Older nightly code lacks the repaired
coverage and cannot be treated as a complete full-stack backup solution. Never
delete good snapshots or rewrite an old checksum list as part of rollback.
