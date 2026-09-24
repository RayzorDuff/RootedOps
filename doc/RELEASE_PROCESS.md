# Release process

`VERSION` is canonical. The README, changelog, and versioned release notes must agree with it. Git tags are milestone markers rather than a requirement for every version bump.

## Incremental development phases

Use a **patch** version bump (`major.minor.patch`) for reviewed incremental phases that advance an open issue without completing a release milestone. Keep versioned release notes so deployed code remains identifiable, but do **not** create a Git tag for these phase-level patch releases.

```bash
make prepare-release VERSION=1.3.1 RELEASE_DATE=2026-09-24
# Complete doc/CHANGELOG.md and releases/v1.3.1/RELEASE_NOTES.md.
make release-check
git diff --check
```

## Issue or milestone completion

When one or more issues are verified complete and the repository reaches a meaningful release milestone, bump the **minor** version and create an annotated `vX.Y.Z` Git tag after the release commit has been pushed.

```bash
make prepare-release VERSION=1.4.0 RELEASE_DATE=2026-09-24
# Complete changelog/release notes, validate, commit, and push first.
make release-check
git diff --check
git tag -a v1.4.0 -m "RootedOps v1.4.0 - <milestone>"
git push origin v1.4.0
```

Major version bumps remain reserved for intentionally incompatible architectural/product changes.

Run release preparation from a clean `main` branch. Preparation changes files only; it does not commit, tag, push, run migrations, restart containers, deploy, or publish a GitHub release. Production deployment remains a separate reviewed operation.

For a coordinated Rooted software milestone, record exact tags for MushroomProcess, SignatureGate, RootedOps, and BookWorks. Coordination records compatibility while each repository retains independent semantic versioning.
