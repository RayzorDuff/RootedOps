# RootedOps 1.5.33

Patch phase; no Git tag. Commerce app version: 0.3.8.

The production dankmushrooms.net API returned Cloudflare HTTP 403 / error 1010 for
Python's default user agent. The same authenticated GET passed with an explicit
RootedOps agent. ERP customer reads/projections and the shared commerce API client
now send `User-Agent: RootedOps-Commerce/1.0`.

Authentication, HTTPS, redirect restrictions and logical store identities are
unchanged. The hostname runbook includes deployed-client readback and transport
rollback instructions. Historical Ecwid order imports are deferred by owner decision.

Validation: local commerce suite (229 tests, one skipped), Python/shell validation,
release metadata and whitespace checks. Production deployment, authenticated reads
using the committed client, and bidirectional profile acceptance remain pending.

After merge, deploy commerce through `bash erpnext/deploy.sh erp.danks.store commerce`,
then follow `doc/dankmushrooms-hostname-standalone.md` section 5. Preserve the old
hostname until both directions of customer sync and remaining cutover connections pass.
