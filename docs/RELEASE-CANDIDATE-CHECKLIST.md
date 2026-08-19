# Final Release Candidate Checklist

This checklist is evidence-driven. Final-release status requires the release candidate to pass exact-head CI/Security, merge under repository policy, and have the release tag verified against the exact final `main` commit.

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

## Release evidence already recorded

- [x] Real Postgres CI integration.
- [x] Real Qdrant lifecycle and cross-tenant negative coverage.
- [x] Representative authenticated production service-API E2E.
- [x] Destructive backup/restore DR drill.
- [x] Bounded real-Qdrant performance guardrail.
- [x] Backend/frontend dependency audit and committed-secret scan gates.
- [x] Production deployment/upgrade/rollback guide merged.
- [x] zworkforce PR #168 merged as `00b1aa3db1c9da15e8eb4e635b455181d1c03213`.
- [x] Final operational/deployment/security documentation audit reconciled against current `main` documentation set.
- [x] Release version determined as `0.1.0`, matching both FastAPI and Admin package version surfaces.
- [x] `CHANGELOG.md` and `docs/RELEASE-NOTES-v0.1.0.md` record the complete S1-S17 production scope.

## Final release work still required

- [ ] Run exact-head CI and Security workflows for this release candidate.
- [ ] Verify no open failing/stale release PR remains.
- [ ] Merge the release candidate under repository policy.
- [ ] Record the final zknowbase `main` SHA.
- [ ] Create and verify tag `v0.1.0` against that exact commit.

Until those final repository operations are complete, the release verdict remains `FINAL RELEASE — BLOCKED`.
