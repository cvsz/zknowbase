# zknowbase v0.2.0 Roadmap

Status: post-release planning and production feedback cycle started 2026-08-21.

## Immutable baseline and compatibility

- The v0.1.0 tag and commit `b27352d64b200b79739653921c82551d4e06b7d6` are immutable release artifacts.
- No v0.2.0 change may rewrite, move, or retag v0.1.0.
- v0.2.0 is additive by default. Existing v0.1.0 API, SDK, storage, and backup formats remain supported unless a reviewed deprecation notice says otherwise.
- Database migrations must be forward-only, restart-safe, and accompanied by a backup, verification, and rollback/restore procedure. Destructive or irreversible migrations require an explicit release exception.
- Backup readers remain backward-compatible with v0.1.0 archives. New writers must document the minimum reader version and preserve tenant ownership/security metadata.
- SDK and governed zworkforce contract changes require versioned fields, tolerant readers, fail-closed authorization, and consumer evidence before release.

## Evidence-driven milestones

| Priority | Milestone | Exit evidence |
| --- | --- | --- |
| P0 | Production feedback intake and triage | Structured issue form, severity/tenant-impact rubric, weekly triage log, and at least one replayable sanitized case |
| P0 | Observability/SLO calibration | Representative workload capture, percentile/error-budget report, calibrated objectives in `docs/OBSERVABILITY-SLO.md`, and no secret/raw-content telemetry |
| P0 | Reliability and DR hardening | Repeatable restore drill, measured RPO/RTO, backup compatibility matrix, and recovery sign-off |
| P1 | Tenant/collection/encryption policy maturity | Documented policy decisions, rotation/restore tests, cross-tenant negative tests, and operational key ownership evidence |
| P1 | Performance/cost optimization | Workload-specific p50/p95/p99, provider/Qdrant attribution, resource/cost envelope, and regression thresholds |
| P1 | SDK/zworkforce evolution | Contract fixture matrix, compatibility tests in both repositories, and least-privilege consumer evidence |
| P1 | Admin UX and operations | Operator task completion evidence for ingest, queue recovery, backup/restore, and audit review |
| P1 | Upgrade/backward compatibility | Versioned migration guide, upgrade rehearsal from v0.1.0, downgrade/restore boundary, and deprecation policy |
| P0 | Security/dependency audits | Exact-head CI/Security success, dependency review, secret scan, and vulnerability disposition |
| P0 | v0.2.0 release gates | All P0 evidence merged, exact-head checks green, release notes/migration guide reviewed, and tag created once |

## Feedback cycle

Every production report uses `docs/PRODUCTION-FEEDBACK.md` or the repository issue form. Triage records impact, affected version/commit, tenant scope without sensitive identifiers, reproducibility, security/privacy implications, and the next evidence-producing action. Reports that contain secrets or personal data must be redacted and rotated before investigation.

Cadence: acknowledge within one business day, assign a severity within two business days, and review open P0/P1 items weekly. A release-blocking issue stays open until its acceptance evidence is linked.

## v0.2.0 release gates

1. v0.1.0 immutability check passes.
2. P0 milestones have merged evidence and exact-head CI/Security checks.
3. Migration and backup compatibility are tested from the v0.1.0 baseline.
4. No unresolved critical/high security finding or cross-tenant isolation regression exists.
5. SLO targets are explicitly marked calibrated, provisional, or unmet.
6. Release notes, upgrade/rollback guidance, known limitations, and consumer contract evidence are reviewed.
