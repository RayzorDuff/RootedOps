# BookWorks → WordPress deployment (phase 1)

This is the supported entry point for **schema v1, media-free** BookWorks WordPress JSON packages. It replaces separate presentation-install and importer commands. It does **not** build BookWorks sources, upload media, change WordPress navigation, or publish anything.

On the BookWorks Mac, build a public-facing profile with `make build-wordpress`, then transfer the generated JSON to the RootedOps server using the existing approved transport. The builder requires a clean tracked Git working tree and embeds its source commit and HTML checksum.

On Linode:

```bash
cd ~/RootedOps
git pull --ff-only origin main
bash scripts/deploy_bookworks_publication.sh \
  --payload /tmp/spiritual-center-wordpress.json \
  --expected-key rooted-psyche-fundraising:spiritual-center \
  --mode check
```

`check` validates the JSON locally, then asks WordPress for a **read-only** plan. It does not install assets or change content.

For a **new or existing draft**, use `--mode stage` only after reviewing the plan. This installs the current presentation files, stages the draft, and checks idempotency. The importer refuses unexpected edits and refuses to change a published page to a draft. A published page with matching content returns `unchanged`.

**Important:** The existing Spiritual Center Fund is already published. Do not run `stage` to update it; published-page revisions need a separate review and release path. `check` remains safe.

## Next phases (not implemented yet)

- Portable media manifest: role, path, SHA-256, MIME, alt text, caption, conceptual-vs-documentary disclosure; transport from BookWorksSources/BookWorksArtifacts without depending on GitHub Actions having Mac files.
- Idempotent WordPress Media Library upload and attachment-role association, including strict `photo`/`concept` roles and no silent defaults.
- Generic WordPress layout adapter for public-facing book editions, separate from the current fundraising-specific presentation.
- Versioned published-page revision workflow with explicit approval, preview, conflict detection, and rollback.
- Automated PHP and shell integration tests in CI against a disposable WordPress instance.
- Eventually an end-to-end Mac build/package/transfer command. No unattended publication.
