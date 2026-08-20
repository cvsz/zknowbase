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

## Failing Required-Check Denial Probe

PR #66, `test: prove protected-main rejects failing required checks`, was opened
solely as a governance probe from protected `main`. Its head was
`131a45b375da41bc978d826d8da361b415786afe` and included an intentionally failing
backend pytest while leaving the other repository checks unchanged.

GitHub CI run `32427160455` recorded the required `backend` job as `failure` while
`frontend`, `performance`, `compose`, and `retrieval-quality` completed
successfully. A normal merge attempt was then sent through GitHub's merge API
with the exact expected head SHA. GitHub rejected the merge with HTTP 405 and
reported both enforcement reasons:

- `At least 1 approving review is required by reviewers with write access.`
- `Required status check "backend" is failing.`

No protection setting was changed or bypassed. PR #66 was closed unmerged after
the denial was observed. This proves the deliberately failing PR half of S18's
acceptance criterion through the same normal merge endpoint used for valid PRs.

## Green Normal-Merge Probe

The remaining S18 acceptance step is a green PR successfully merging through the
same protected path after current required checks and an independent approving
review. PR #62 itself is the canonical green probe once its exact current head
passes CI/Security, receives a current non-stale approval, and GitHub accepts its
normal merge.

## Acceptance Mapping

- A deliberately failing PR cannot merge through the normal path: proven by PR
  #66, failed required `backend` check, exact-head merge rejection, and unmerged
  closure.
- A green PR can proceed through the normal path after required review and code
  owner gates are satisfied: pending successful protected merge of PR #62.
- Direct `main` pushes, force pushes, and branch deletion are disabled by policy.
- Emergency changes use the documented hotfix process and must record any
  temporary governance change as explicit release evidence.
