# RootedOps 1.5.25

RootedOps Issue #1 hardens ERPNext deployment service restarts.

The deployment script now restarts and verifies ERPNext WebSocket and frontend
services in addition to backend, queue workers, and scheduler. The frontend is
restarted after backend/WebSocket so nginx resolves live upstreams after an
application deployment.

This follows the first successful production SignatureGate cash-deposit
synchronization, which created Journal Entry `ACC-JV-2026-00430`.

No Git tag is created because Issue #1 remains open.
