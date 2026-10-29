# RootedOps v1.5.26

Release date: 2026-10-19

Incremental infrastructure support for SignatureGate v1.2.0 private Google Drive paper storage. n8n now receives SIGNATUREGATE_PAPER_DRIVE_FOLDER_ID and SIGNATUREGATE_PAPER_STORAGE_PROVIDER; the compatibility default remains nocodb. Google OAuth and actual folder/header credentials are configured privately in n8n/Appsmith. Existing service definitions and Header Auth choices are retained.

Follow doc/SIGNATUREGATE_PAPER_STORAGE.md for environment setup and recreation of n8n only. No ERPNext deployment, workflow activation, live upload or release tag is performed by preparation. Release metadata and structured Compose checks pass; runtime Google folder/retrieval and coordinated dependency release acceptance remain open.
