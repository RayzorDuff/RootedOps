# Rooted Psyche WordPress backup operations

Production WordPress runs in `docker-rootedpsyche-wordpress-1` with database `docker-rootedpsyche-wordpress-db-1`. The production homepage is https://rootedpsyche.org. Back up **both** the MariaDB database and `wp-content` (themes, plugins, uploaded media, and must-use plugins). Keep the separate pre-cutover Grav backup and Nginx configuration until rollback is retired.

## One-time backup validation

Run on the Linode:

```bash
cd ~/RootedOps
git pull --ff-only origin main
sudo bash scripts/backup_rootedpsyche_wordpress.sh
sudo ls -lah /var/backups/rootedpsyche-wordpress/
```

Each successful run creates a timestamped directory with `wordpress.sql`, `wp-content.tar.gz`, and `SHA256SUMS`. The script uses a lock, a private staging directory, restrictive permissions, dump sanity check and SHA256 validation before publishing a backup. The default retention is 30 days; override with `ROOTEDPSYCHE_WP_BACKUP_RETENTION_DAYS`. Retention is not a substitute for off-server backups.

## Enable daily backup only after first run succeeds

```bash
sudo crontab -e
```

Add this line (daily at 02:20 **server local time**):

```cron
20 2 * * * /bin/bash /home/dankmushrooms/RootedOps/scripts/backup_rootedpsyche_wordpress.sh >> /var/log/rootedpsyche-wordpress-backup.log 2>&1
```

Review with `sudo crontab -l`. Do not place passwords in cron. Docker reads the existing MariaDB container's environment.

## Off-server copy and restoration rehearsal

Arrange an encrypted off-server copy with separate retention and access controls; the local backup alone does not protect against server failure. Periodically restore to an **isolated test database and WordPress instance**, never overwrite the production database to test a backup. Confirm that the site loads, media appears, and the Givebutter widget renders. The script checks file integrity but does not prove a full restoration.

Avoid `docker compose down -v`, which would delete persistent database/media volumes. WordPress's installed site URLs are production HTTPS URLs; use a test URL and database-safe URL migration in a restoration rehearsal.
