# RootedOps v1.5.6

Release date: 2026-09-27

## Summary

Issue #9 Phase 1 is narrowed to the minimal LibreChat runtime required for the
interactive OpenRouter workbench. MongoDB remains required; Meilisearch and
LibreChat RAG/pgvector are deferred. BookWorks document processing remains
Mac-local and is not a Linode runtime dependency.

## Changes

- Removed the LibreChat Meilisearch service from the initial Docker deployment.
- Removed Meilisearch-specific environment and persistent-volume configuration.
- Kept LibreChat, MongoDB, server-side OpenRouter credentials, and deterministic model specifications.
- Updated deployment documentation and validation criteria.
- Preserved RAG/pgvector as an optional future phase rather than a current Linode workload.
