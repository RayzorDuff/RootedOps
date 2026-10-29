# SignatureGate paper storage environment

SignatureGate owns its database migrations and the authenticated SignatureGate - Paper Agreement Upload workflow. RootedOps passes the infrastructure configuration into n8n. The optional Google Drive branch uses OAuth authorized by the designated organization Google account and a private folder in My Drive. Configure the OAuth credential in n8n; do not put OAuth tokens or client secrets into Git or this file. Review the folder's inherited access and share only with intended reviewers.

Add the actual private folder ID to ~/RootedOps/.env:

```dotenv
SIGNATUREGATE_PAPER_DRIVE_FOLDER_ID=replace_with_private_folder_id
SIGNATUREGATE_PAPER_STORAGE_PROVIDER=nocodb
```

Only the folder ID is needed to enable explicit google_drive uploads. Keep nocodb as the compatibility default for older callers, or deliberately set google_drive when that is the intended default for callers that omit a provider. The current Appsmith selector sends its choice explicitly. Folder IDs, account addresses and credentials are private deployment mappings; example files contain no actual values.

After pulling this change and editing .env, apply only the n8n service environment:

```bash
cd ~/RootedOps &&
git pull --ff-only &&
sudo docker compose --env-file ./.env -f docker/docker-compose.yml config --quiet &&
sudo docker compose --env-file ./.env -f docker/docker-compose.yml up -d --no-deps n8n
```

Recreation briefly restarts n8n and retains its persistent volume/credentials. It does not deploy ERPNext or restart unrelated services. Do not print the rendered Compose configuration or .env when returning evidence.

Update the existing development paper workflow in place from SignatureGate, preserving Header Auth and test database/storage credentials. Select its Google Drive OAuth2 credential, use SIGNATUREGATE_PAPER_DRIVE_FOLDER_ID as Parent Folder and publish it normally. The generic legacy NocoDB uploader is retained. Do not create a duplicate active webhook at the same path.

Run SignatureGate/releases/v1.2.0/validate_paper_agreement_test.sh before frontend/workflow rollout, with the development paper workflow paused during migration. Then test one synthetic no-email Participant upload, private Drive retrieval and independent reviewer approval. Return only exit codes and pass/fail, never document bytes, file IDs, folder IDs or secrets. SignatureGate/n8n/GOOGLE_DRIVE_PAPER_STORAGE.md contains the current workflow/provider and JSON payload details.

This patch is incremental infrastructure wiring, not a final coordinated RootedOps release or proof of installed OAuth/storage access. The existing cash-deposit ERP integration and broader SignatureGate production dependency gates remain separate.
