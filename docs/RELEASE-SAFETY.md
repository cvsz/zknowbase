# Release Safety and Repository Governance

This repository uses `main` as the protected release branch. Normal release and
hotfix work must move through pull requests; direct pushes to `main`, force
pushes, and branch deletion are not part of the normal path.

## Required Merge Path

Pull requests targeting `main` must satisfy the protected-branch policy:

- branch must be up to date before merge;
- required CI contexts must pass: `backend`, `retrieval-quality`, `performance`,
  `frontend`, and `compose`;
- required Security contexts must pass: `python-dependencies`,
  `frontend-dependencies`, `secrets`, and `dependency-review`;
- at least one approving review is required;
- code owner review is required for owned paths;
- stale reviews are dismissed after new pushes;
- unresolved conversations block merge;
- administrators are included in enforcement.

The local evidence command for the configured policy is:

```bash
gh api repos/cvsz/zknowbase/branches/main/protection \
  --jq '{required_status_checks: .required_status_checks.contexts, strict: .required_status_checks.strict, enforce_admins: .enforce_admins.enabled, required_pull_request_reviews: .required_pull_request_reviews, required_conversation_resolution: .required_conversation_resolution.enabled, allow_force_pushes: .allow_force_pushes.enabled, allow_deletions: .allow_deletions.enabled}'
```

## Emergency Procedure

Emergency changes still require a pull request unless GitHub itself or a
repository-administration incident makes the normal path unavailable.

1. Open a hotfix branch from current `main`.
2. Keep the patch narrowly scoped to the production blocker.
3. Preserve tenant, authentication, backup, and local-first guarantees.
4. Run the narrowest relevant local validation before opening the PR.
5. Let the required CI and Security workflows run on the exact PR head.
6. Obtain the required reviewer/code-owner approval.
7. Merge only after the protected-branch checks are green.
8. Record the incident, commit SHA, validation evidence, and follow-up work in
   release evidence or the relevant runbook.

If the protected-branch policy must be changed for an incident, record who made
the change, the exact setting changed, why it was necessary, when it was
restored, and what compensating verification was run. Silent bypasses are not
allowed.

## Tag and Provenance Procedure

Release tags must point at the approved release commit after required checks and
review have passed. Before publishing a release, record:

- release commit SHA;
- CI and Security workflow run IDs for the exact release commit;
- relevant integration evidence for Qdrant/Postgres and backup/recovery;
- changelog and release notes path;
- rollback or hotfix instructions if the release must be withdrawn.
