# Release process

`VERSION` is canonical. The README, changelog, versioned release notes, and `vX.Y.Z` tag must agree with it.

```bash
make prepare-release VERSION=1.1.1 RELEASE_DATE=2026-08-13
# Complete doc/CHANGELOG.md and releases/v1.1.1/RELEASE_NOTES.md.
make release-check
git diff --check
```

Run this from a clean `main` branch. Preparation changes files only; it does not commit, tag, push, run migrations, restart containers, deploy, or publish a GitHub release. Production deployment remains a separate reviewed operation.

For a coordinated Rooted software release, record exact tags for MushroomProcess, SignatureGate, RootedOps, and BookWorks. Coordination records compatibility while each repository retains independent semantic versioning.
