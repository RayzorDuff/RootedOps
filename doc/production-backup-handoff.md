# Production backup changes and operator handoff

Merge RootedOps PR #21 first. No production backup or deployment was executed by
this development work. Production is 45.33.107.185; the test restore path is for
a separate fresh host. Do not install the new test NGINX defaults on production.
Existing local `.env`, installed NGINX and merchant configuration stay in place.

The backup fix resolves each actual named volume from the running container mount,
rather than assuming unprefixed names. Docker previously created missing empty
volumes silently. This explains the empty attached Appsmith/n8n archives; they
contain only `.` and cannot recover application data. New backups fail on missing
sources, empty application archives or unsafe archive paths. Redis caches may be
empty. Files are private by default; remote snapshot verification precedes pruning.

n8n and Appsmith are briefly stopped for their SQLite/embedded database snapshots,
then restarted only if previously running. The failure trap retries restarting
paused containers. Scheduling cold backups and optional Minecraft interruption
retain their existing behavior. Choose a maintenance window. ERPNext SQL uses a
transactional dump, but its files and SQL are not a single coordinated point-in-time
snapshot; quiesce ERP writes for recovery-grade consistency. Retain original ERP
site encryption keys and the n8n encryption key in the secured backup.

On production, after review/merge (adapt the checkout path if different):

```bash
cd /opt/RootedOps
git status --short
# Continue only with a clean, reviewed deployment checkout on main.
git pull --ff-only origin main
bash -n backup/backup-stack.sh backup/volume-tools.sh
sudo docker ps --format 'table {{.Names}}\t{{.Status}}'
# Confirm existing .env points to the correct rclone configuration/remote.
# The script requires configured DB containers; it fails rather than inventing backups.
# Run in a protected log directory; logs/archives are not public artifacts.
sudo install -d -m 700 /var/log/rootedops-backups
sudo sh -c 'umask 077; SKIP_BACKUP_PRUNE=true bash /opt/RootedOps/backup/backup-stack.sh > /var/log/rootedops-backups/manual.log 2>&1'
sudo tail -n 20 /var/log/rootedops-backups/manual.log
```

`SKIP_BACKUP_PRUNE=true` preserves existing remote snapshots during this recovery
rehearsal. Review retention separately. The successful log identifies the timestamp
and remote path. Fetch that complete timestamp directory using the same configured
rclone remote; keep `meta/.env`, database dumps, archives and `SHA256SUMS` together.
Verify `sha256sum -c SHA256SUMS` inside the recovered directory before the fresh
Linode restore. Do not send credentials or archive contents in a GitHub issue.

Required new artifacts for the pending rehearsal: nonempty `n8n_data.tgz`, nonempty
`appsmith_stacks.tgz`, the MushroomProcess dump, and (for ERP recovery) the ERP SQL
and sites archive. Original application versions/image digests must be recorded so
the restored application code matches the data schema. See
[test-environment-restore.md](test-environment-restore.md).
