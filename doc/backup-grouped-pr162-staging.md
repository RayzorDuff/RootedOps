# Issue #160 — Isolated grouped-backup staging (PR #162)

This is an **experimental** change on [RootedOps PR #162](https://github.com/RayzorDuff/RootedOps/pull/162). Keep the production `~/RootedOps` working tree, `.env`, nightly `07:30 UTC` cron entry and global backup untouched. The grouped feature is opt-in; default `BACKUP_QUIESCE_MODE=global`. Never use `git pull` in production to test an open PR, or enable the grouped setting in the production `.env`.

## Fetch a pinned review revision into a separate tree (no production checkout changes)

Run as `dankmushrooms` on the Linode. This uses the same authenticated Git remote already configured in the production checkout. Never copy or commit live credentials into the branch. Set paths as shown; do not build from a moving branch after reviewing its SHA.

```bash
set -euo pipefail
PROD=/home/dankmushrooms/RootedOps
STAGE=/home/dankmushrooms/rootedops-staging/issue-160-pr-162
mkdir -p "$(dirname "$STAGE")"
chmod 700 "$(dirname "$STAGE")"
test ! -e "$STAGE"
git clone --no-checkout "$(git -C "$PROD" remote get-url origin)" "$STAGE"
git -C "$STAGE" fetch origin refs/pull/162/head
git -C "$STAGE" switch --detach FETCH_HEAD
git -C "$STAGE" rev-parse HEAD
# Private source configuration is read by the staging script, not modified.
ln -s "$PROD/.env" "$STAGE/.env"
test -r "$STAGE/.env"
cd "$STAGE"
bash -n backup/backup-stack.sh backup/volume-tools.sh
python3 -m py_compile scripts/recovery_bundle.py
python3 -m unittest discover -s tests -p 'test_recovery_bundle.py' -v
```

For a **later PR revision**, preserve local staging logs and verify the tree is clean before refreshing with `git -C "$STAGE" fetch origin refs/pull/162/head && git -C "$STAGE" switch --detach FETCH_HEAD`. Record the reviewed SHA for each acceptance.

## Live staging outcome and inventory-drift follow-up (2026-11-28)

The first live grouped rehearsal reached the end of the `operations` capture, restarted its paused services, and then stopped before `documents` with `Drift: binds (mount inventory changed)`. No staged backup was published. Production's original global cron and snapshot remain unchanged.

The original verifier compared ordered bind records that received positional archive filenames from Docker's mount enumeration. An unchanged mount set may be enumerated in a different order after stop/start. The PR now compares the **identity and content** of each bind (project/service/destination, host source, read-only status) independently of enumeration order while preserving the original manifest's archive numbering. It still refuses missing, added or genuinely changed binds and reports service/destination without printing private host paths.

After fetching the latest PR head, first run:

```bash
cd /home/dankmushrooms/rootedops-staging/issue-160-pr-162
python3 -m unittest tests.test_recovery_bundle.InventoryTests.test_bind_mount_reordering_is_not_drift_but_source_change_is -v
python3 -m unittest discover -s tests -p 'test_recovery_bundle.py' -v
```

Only rerun the grouped live backup after these tests and the exact-commit GitHub recovery CI pass. If the next run reports an actual bind source or access change, **stop** and inspect that specific service; do not bypass the invariant.

## Read-only / no-stop inventory and image preflight

`BACKUP_IMAGE_PLAN_ONLY=true` returns after runtime inventory and image provenance selection, before pausing any applications or writing/uploading any SQL/volume snapshot. The staging runner explicitly requires a separate remote root and non-pruning mode even for preflight. The remote target is a distinct path on the existing configured rclone remote; this command does **not** upload there.

```bash
cd /home/dankmushrooms/rootedops-staging/issue-160-pr-162
umask 077
BACKUP_SOURCE_ROOT=/home/dankmushrooms/RootedOps \
BACKUP_REMOTE_ROOT_OVERRIDE='signaturegate-gdrive-free:SignatureGateBackups/rootedops-issue160-staging' \
BACKUP_PREFIX_OVERRIDE=rootedops-issue160 \
SKIP_BACKUP_PRUNE=true BACKUP_IMAGE_PLAN_ONLY=true BACKUP_QUIESCE_MODE=grouped \
bash backup/backup-stack.sh > "$HOME/issue160-image-preflight.log" 2>&1
echo "Preflight exit: $?"
tail -n 25 "$HOME/issue160-image-preflight.log"
```

Do not share complete manifests, `.env`, resolved Compose config, secrets, or archive data publicly.

## Controlled live group backup (maintenance window ONLY)

This **will temporarily stop selected production containers**, but uses the separate staged scripts and **will not** modify the production Git tree, overwrite the production backup timestamp, or execute remote pruning. Schedule this away from the nightly cron and commerce operations. Both jobs use the same default host staging lock (from `.env`) to prevent overlap. Only execute after PR checks and the preflight pass, and after confirming no external write activity or in-flight checkouts. This backup produces independent application-group consistency rather than a cross-application atomic point-in-time snapshot.

```bash
cd /home/dankmushrooms/rootedops-staging/issue-160-pr-162
umask 077
BACKUP_SOURCE_ROOT=/home/dankmushrooms/RootedOps \
BACKUP_REMOTE_ROOT_OVERRIDE='signaturegate-gdrive-free:SignatureGateBackups/rootedops-issue160-staging' \
BACKUP_PREFIX_OVERRIDE=rootedops-issue160 \
SKIP_BACKUP_PRUNE=true BACKUP_QUIESCE_MODE=grouped \
bash backup/backup-stack.sh > "$HOME/issue160-grouped-acceptance.log" 2>&1
result=$?
echo "Grouped backup exit: $result"
tail -n 40 "$HOME/issue160-grouped-acceptance.log"
```

Use a shell **without `set -e`** for the final command if you want `result=$?` printed on error. Failure triggers the existing application restart trap, and no successful backup is published or pruned. Confirm the host service health after any test run, including errors.

Required acceptance: every group logs a complete/restarted marker; previously stopped containers are not started; all SQL/volume/bind archives in the format-2 inventory are present; `validate` and SHA256SUMS pass; rclone reports **zero differences** against the staging timestamp; independent clean-host restore acceptance occurs through the existing Authentik/Appsmith rehearsal issue; and there are no uncontrolled order/reservation or shared-state inconsistencies. Do not change cron to grouped mode or close #160 before these gates pass.

## Snapshot boundaries

- **operations:** ERPNext workers/frontend and Redis, both WordPress sites, MushroomProcess/SignatureGate/NocoDB databases, NocoDB, n8n, Appsmith; captures operational SQL and application volumes.
- **documents:** Documenso writers + Documenso PostgreSQL, certificate data.
- **communications:** Listmonk and MailFlow writers + SQL.
- **identity:** Authentik server/worker + PostgreSQL, optional media/certs.
- **chat:** both LibreChat instances and MongoDB raw volumes.
- **scheduling:** Tymeslot embedded PostgreSQL and Rallly web/DB/Garage volumes.

**Cross-boundary caution:** SignatureGate can invoke Documenso; n8n and order webhooks can issue writes to other groups. Pausing writers in one group does not guarantee every cross-group transaction is frozen. A deterministic cross-boundary quiescence/acceptance plan is required before replacing the production-wide backup, and restore acceptance must prove these boundaries are adequate. Do not enable production grouped mode based only on unit tests or a successful upload.
