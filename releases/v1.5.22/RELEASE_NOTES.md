# RootedOps 1.5.22

RootedOps Issue #1 hardens n8n-to-ERPNext transport for same-host integrations.

The SignatureGate cash-deposit synchronization and ERP bank-account lookup
workflows now prefer the Docker-network ERPNext frontend instead of routing
through the public Cloudflare hostname. Public ERPNext remains a fallback.

Both workflows retry transient internal HTTP failures. Existing RootedOps
idempotency continues to prevent duplicate accounting if a response is lost
after ERPNext has already processed an event.

No Git tag is created because Issue #1 remains open.
