# Contributing to RootedOps

RootedOps contains Docker services, deployment/bootstrap and restore procedures, ERPNext and payroll functionality, and website integrations. Use extra care with changes to operational services, configuration templates, and recovery scripts.

## Change size, risk, and review policy

Decide whether a change needs a pull request (PR) by **risk and scope**, not by a fixed line-count threshold.

- **Trivial:** spelling, comments, README/CONTRIBUTING clarifications, formatting — a direct commit to `main` is allowed after checking the diff.
- **Small, localized:** a focused syntax correction or narrow bug fix, even across a few scripts — a direct commit to `main` is allowed after relevant validation.
- **Substantial:** features, multiple subsystems, or changes whose side effects are hard to review — use a topic branch and PR, then notify the repository owner and leave the final merge to them.
- **High risk, regardless of lines changed:** significant file deletion/renaming, Docker/infrastructure, deployment, bootstrap/restore or backup workflows, database schema/data migration, authentication/permissions, payroll/financial processing, or production security — use a topic branch and PR. Do not push such changes straight to `main`.

For any substantial/high-risk PR:

1. Branch from current `main`, keep unrelated changes out, and document the scope and risk.
2. Inspect `git diff --stat`, `git diff --check`, and the complete changed/deleted/renamed file list. Specifically verify that all deletions are intended. For broad cleanup, compare against the pre-change tree before committing.
3. Run applicable lint, tests, validation, and build checks; record what passed and what could not be run.
4. Open the PR, make it ready for review (not a draft), include issue references and a concise validation/rollback summary, and notify the owner with its link.
5. **Do not self-merge:** the repository owner reviews and performs the final merge. Respond to PR review comments and revalidate as needed.

## Branch protection and review limitations

The `main` ruleset is intended to block branch deletion and force pushes, with active enforcement and no bypass. The baseline ruleset does **not** itself mandate PRs for substantial changes, CI checks, or conversation resolution. Those requirements above are contributor workflow conventions; do not represent them as GitHub-enforced. If CI status checks are subsequently required, configure actual reliable checks for this repository and verify the effect on direct commits. Do not rewrite protected branch history to repair a mistake.

## RootedOps validation focus

For infrastructure or service changes, enumerate affected Compose services and environment variables, check for accidentally removed files, and describe both clean-install and restore-path implications. Never commit secrets or operational credentials. For payroll/NACHA changes, keep real bank and employee account information out of public commits and test artifacts.
