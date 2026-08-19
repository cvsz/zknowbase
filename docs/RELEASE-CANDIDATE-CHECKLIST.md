# Final Release Candidate Checklist

This checklist is intentionally evidence-driven. It must not be converted to a final-release claim until every item is backed by current-main CI/security evidence and the final release commit/tag.

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

## Final release work still required

- [ ] Reconcile the final operational/deployment/security documentation audit against current main.
- [ ] Determine the release version from repository history and compatibility policy.
- [ ] Update CHANGELOG/release notes with the complete S1-S17 production scope.
- [ ] Run exact-head CI and Security workflows for the release candidate.
- [ ] Verify no open failing/stale release PR remains.
- [ ] Merge the release candidate under repository policy.
- [ ] Record the final zknowbase main SHA.
- [ ] Create and verify the release tag against that exact commit.

Until these final items are complete, the release verdict remains `FINAL RELEASE — BLOCKED`.
