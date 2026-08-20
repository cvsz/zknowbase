# Release Governance and Break-Glass Procedure

This document defines the repository-side governance contract for `cvsz/zknowbase`. Repository rulesets or branch-protection settings are authoritative for enforcement; this document does not claim settings are enabled unless GitHub evidence proves it.

## Normal merge path

Changes to `main` must flow through a pull request. A normal merge is permitted only when the repository-required CI and Security checks for the exact PR head are successful and all required review policy is satisfied.

The expected release-sensitive workflows are:

- `.github/workflows/ci.yml` (`CI`)
- `.github/workflows/security.yml` (`Security`)

A stale successful run from an earlier commit must not be treated as evidence for a newer PR head.

`main` should be configured to reject force pushes and branch deletion. Direct pushes to `main` should be prohibited by the active repository ruleset/branch-protection policy.

## Ownership

`.github/CODEOWNERS` records ownership for backend security/tenant boundaries, frontend authentication/server-proxy paths, operations/deployment/recovery, workflows, and release evidence. CODEOWNERS is review routing metadata; it does not replace required-review enforcement in repository settings.

## Break-glass procedure

Break-glass is reserved for an active production incident where waiting for the normal path materially increases impact. It must not be used for convenience, release deadlines, flaky tests, or dependency conflicts.

1. Record the incident identifier, scope, operator, reason normal governance cannot be used, and intended minimal change.
2. Preserve all available CI/Security evidence. A failing required check may not be reclassified as passing.
3. Make the smallest reversible change needed to contain or recover the incident.
4. Do not weaken tenant isolation, authentication/authorization, upload/retrieval fail-closed behavior, secret boundaries, backup integrity, or auditability merely to restore service.
5. After stabilization, open a PR containing the exact emergency diff or a reconciliation commit, run the normal CI/Security suite, obtain normal review, and record evidence.
6. If an emergency repository-setting bypass was required, restore the normal rules immediately after stabilization and record the setting change and restoration in the incident evidence.
7. Add a post-incident note identifying root cause, follow-up tests, and any governance improvements.

Break-glass does not make an unvalidated change release evidence. A release/tag may only use a commit that satisfies the normal release gate.

## Release and tag provenance

For every production release:

1. identify the exact approved release-candidate commit;
2. require exact-head CI and Security success;
3. merge under repository policy;
4. record the resulting immutable release commit SHA;
5. create the version tag only after the approved release commit exists;
6. verify the remote tag resolves to the intended commit (for annotated tags, verify the peeled `^{}` target);
7. record PR numbers, workflow run identifiers, security evidence, final commit SHA, and tag in release evidence.

Moving or reusing a published production tag is prohibited. A correction requires a new version.

## Post-release hotfix

A hotfix starts from the released lineage or current `main`, as appropriate for the supported release policy, and uses a dedicated focused PR. It must include regression coverage for the defect, complete applicable CI/Security gates, document compatibility/operational impact, and use a new semantic version/tag when a production artifact changes.

A hotfix must preserve the local-first architecture and existing security/tenant guarantees. Direct Qdrant access from consumers, browser-visible service credentials, or paid/hosted default dependencies are not acceptable hotfix shortcuts.

## Required GitHub settings evidence for S18 completion

S18 must remain incomplete until GitHub-observable evidence proves all of the following on `main`:

- pull-request-only normal changes;
- current CI and Security checks required before merge;
- force push prohibited;
- branch deletion prohibited;
- a deliberately failing PR cannot merge normally;
- a green PR can merge normally.

Documentation and CODEOWNERS alone are not evidence that these server-side controls are enabled.
