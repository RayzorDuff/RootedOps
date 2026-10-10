# RootedOps 1.5.23

RootedOps Issue #1 corrects the same-host n8n to ERPNext transport path.

n8n now defaults `ERPNEXT_INTERNAL_URL` to
`http://erpnext-backend:8000`, bypassing the ERPNext frontend nginx
container for authenticated API calls on the Docker network.

The existing SignatureGate n8n workflows already consume
`ERPNEXT_INTERNAL_URL`; they do not need to be re-imported for this change.
After pulling, recreate only the n8n container so it receives the corrected
environment value.

This patch changes infrastructure configuration only. No ERPNext application
deployment is required.

No Git tag is created because Issue #1 remains open.
