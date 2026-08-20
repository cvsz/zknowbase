# S18 Repository Governance Evidence

Date: 2026-08-20

## Scope

S18 adds repository governance and release-safety controls for `main` without
weakening the local-first runtime, tenant isolation, authentication, backup, or
CI/Security guarantees from the completed v0.1.0 baseline.

## Remote Policy Evidence

`main` branch protection was configured through the GitHub branch protection API.
The verified policy requires pull requests, current required checks, code-owner
review, stale-review dismissal, conversation resolution, and administrator
enforcement. Force pushes and branch deletion are disabled.

Verified configuration summary:

```json
{
  "allow_deletions": false,
  "allow_force_pushes": false,
  "enforce_admins": true,
  "required_conversation_resolution": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "require_last_push_approval": false,
    "required_approving_review_count": 1
  },
  "required_status_checks": [
    "backend",
    "retrieval-quality",
    "performance",
    "frontend",
    "compose",
    "python-dependencies",
    "frontend-dependencies",
    "secrets",
    "dependency-review"
  ],
  "strict": true
}
```

Evidence command:

```bash
gh api repos/cvsz/zknowbase/branches/main/protection \
  --jq '{required_status_checks: .required_status_checks.contexts, strict: .required_status_checks.strict, enforce_admins: .enforce_admins.enabled, required_pull_request_reviews: .required_pull_request_reviews, required_conversation_resolution: .required_conversation_resolution.enabled, allow_force_pushes: .allow_force_pushes.enabled, allow_deletions: .allow_deletions.enabled}'
```

## Local Repository Evidence

- `.github/workflows/ci.yml` defines backend, retrieval-quality, performance,
  frontend, and compose checks.
- `.github/workflows/security.yml` defines Python dependency audit, frontend
  dependency audit, Gitleaks history scanning, and dependency-review for pull
  requests.
- `.github/CODEOWNERS` defines default ownership and release-sensitive path
  ownership for backend security/auth/tenant code, frontend auth/proxy code,
  operations/deployment/recovery/observability files, workflows, release
  planning, changelog, and release evidence.
- `docs/RELEASE-SAFETY.md` documents required merge, emergency, hotfix, tag, and
  provenance procedures.

## Current Pull Request Evidence

At configuration time, open release-cycle documentation PRs targeting `main`
reported `mergeStateStatus: CLEAN` and successful CI/Security check rollups.
They still require the configured review and conversation gates before normal
merge.

## Acceptance Mapping

- Failing PRs cannot merge through the normal path because every PR targeting
  `main` must satisfy the listed current required checks, review, code-owner,
  up-to-date, and conversation-resolution gates.
- Green PRs can proceed through the normal path after required review and code
  owner gates are satisfied.
- Direct `main` pushes, force pushes, and branch deletion are disabled by policy.
- Emergency changes use the documented hotfix process and must record any
  temporary governance change as explicit release evidence.
