# Final Release Candidate Checklist

This checklist is evidence-driven. Final-release status requires the release candidate to pass exact-head CI/Security, merge under repository policy, and have the release tag verified against the exact release commit.

## Architecture and security

- [x] Local-first Ollama/Qdrant/SQLite default remains intact.
- [x] Optional self-hosted Postgres HA path exists.
- [x] No Redis/Celery/managed queue is required.
- [x] Local upload validation and optional ClamAV fail closed before parsing.
- [x] Local Admin auth/RBAC and optional self-hosted OIDC are implemented.
- [x] Scoped service keys are hash-only, revocable, rotatable, and tenant-bound.
- [x] Shared Qdrant collection enforces authenticated-tenant payload boundaries.
- [x] Native backup encryption and tenant-aware DR evidence exist.
- [x] Local OpenTelemetry/Prometheus/Grafana observability and initial SLOs exist.
- [x] Governed zworkforce retrieval is merged through the service API only.

## Release evidence

- [x] Real Postgres CI integration.
- [x] Real Qdrant lifecycle and cross-tenant negative coverage.
- [x] Representative authenticated production service-API E2E.
- [x] Destructive backup/restore DR drill.
- [x] Bounded real-Qdrant performance guardrail.
- [x] Backend/frontend dependency audit and committed-secret scan gates.
- [x] Production deployment/upgrade/rollback guide merged.
- [x] zworkforce PR #168 merged as `00b1aa3db1c9da15e8eb4e635b455181d1c03213`.
- [x] Final operational/deployment/security documentation audit reconciled against the release documentation set.
- [x] Release version determined as `0.1.0`, matching both FastAPI and Admin package version surfaces.
- [x] `CHANGELOG.md` and `docs/RELEASE-NOTES-v0.1.0.md` record the complete S1-S17 production scope.
- [x] Release-candidate exact head `e9ea3d69fca21bf21b3323cd289f1b5edab3787a` passed CI run `32256200249` and Security run `32256200225`.
- [x] No open failing/stale release PR or open release issue remained at reconciliation.
- [x] Release candidate merged through PR #49 under repository policy.
- [x] Release commit recorded as `b27352d64b200b79739653921c82551d4e06b7d6`.
- [x] Tag `v0.1.0` is resolvable against the release repository state at commit `b27352d64b200b79739653921c82551d4e06b7d6`.

## Final verdict

`v0.1.0` satisfies the evidence-backed S1-S17 production release contract. This post-release documentation reconciliation does not alter runtime behavior or the already-tagged release artifact.

**FINAL RELEASE — APPROVED**
