# Nightly full-stack recovery bundle

The November 10 restore rehearsal exposed a producer/consumer defect: the nightly
job saved image names but not custom runtime images, omitted the independently
deployed Dank WordPress site and both LibreChat installations, and had no
completeness inventory. The full restorer could silently omit missing archives.
Passing SHA256SUMS proved only that the files present had not changed.

The repaired **existing nightly job** produces a new, complete timestamp directory.
Do not supplement the old `20261110-231728` snapshot with separately exported
images. Keep that set unchanged as historical evidence and use a fresh snapshot
for the next attempt. No production backup or restore is executed by this commit.

## What the nightly job now captures

- `meta/recovery-bundle.json`: format version, explicit installed/not-installed
  groups, actual source container/mount identities, immutable image IDs and every
  required recovery payload. Raw container environments are never serialized.
- `images/runtime-images.tar.gz`: one Docker image export containing all unique
  image IDs actually used by those services, including custom ERPNext/Documenso
  and older versions behind floating tags. Production images are never retagged.
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

Image export precedes the application pause; image validation, remote upload and
retention follow the restart. Snapshots now include image bytes and are larger:
allow sufficient local staging space, backup storage and transfer time. Image
layers are deduplicated within the one Docker export, not across nightly remote
snapshots. The existing retention policy is unchanged, and this first manual run
disables pruning. A single local lock prevents cron/manual backup overlap.

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

Preparation loads the exact saved runtime images, verifies their identities and
pins only the already isolated generated Compose files. It never starts services,
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

Regression coverage includes a simulated complete nightly backup, SQL/image/
volume coverage, explicit absence, corrupt/missing payload refusal, exact image
pinning, source identity drift, previously stopped apps, failure-path restarts and
no-upload-on-failure. CI also exercises native Docker image save/gzip/load and the
existing stopped-volume recovery fixture. Full production backup/recovery awaits
the owner-generated fresh snapshot and the subsequent isolated acceptance run.

To roll back code, revert this change through review, leaving existing snapshots
and generated test credentials intact. Older nightly code lacks the repaired
coverage and cannot be treated as a complete full-stack backup solution. Never
delete good snapshots or rewrite an old checksum list as part of rollback.
