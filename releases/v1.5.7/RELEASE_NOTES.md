# RootedOps v1.5.7

Release date: 2026-09-27

## Issue #9 — LibreChat GitHub MCP development access

This incremental Issue #9 phase adds read-only GitHub repository access to the four
Developer model specs in LibreChat.

### Added

- Hosted GitHub MCP server configuration using Streamable HTTP.
- `repos`, `issues`, and `pull_requests` toolsets.
- Explicit GitHub MCP read-only mode.
- `GITHUB_MCP_TOKEN` runtime secret configuration.
- GitHub MCP assignment to RootedOps Developer, MushroomProcess Developer,
  SignatureGate Developer, and BookWorks Developer.
- Documentation for the four repository boundaries.

### Repository boundary

The GitHub PAT should itself be restricted to:

- `RayzorDuff/RootedOps`
- `RayzorDuff/MushroomProcess`
- `RayzorDuff/SignatureGate`
- `RayzorDuff/BookWorks`

No GitHub credential is committed to RootedOps.

### Versioning

This is an incremental phase of open Issue #9, so the patch version advances to
`1.5.7` without creating a Git tag.
