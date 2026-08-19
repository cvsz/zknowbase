# zworkforce Integration Release Evidence

## Immutable repository references

- zknowbase baseline main: `b35f32513932aa76fe59265911f829d3cea2e5d4`
- zworkforce governed integration PR: `cvsz/zworkforce#168`
- zworkforce exact PR head: `e8c4cb1c519f1c53359c263839c2601150b78846`
- zworkforce merge/main commit: `00b1aa3db1c9da15e8eb4e635b455181d1c03213`

## Production boundary

zworkforce consumes zknowbase only through the zknowbase service API. Governed agent execution uses the read-only `knowledge_search` and `knowledge_ask` ToolExecutor tools; it does not access Qdrant directly.

Production retrieval credentials must be dedicated zknowbase service keys with only the `knowledge:read` scope. Credentials remain in the zworkforce server process secret boundary and are bound to a single tenant or supplied through an operator-controlled per-tenant credential map. Missing tenant credentials fail closed before retrieval.

Governed requests propagate versioned tenant, actor, agent, tool, policy context, request ID, and trace ID metadata. zknowbase authenticates the service key independently and keeps the authenticated principal tenant authoritative. Consumer context cannot select a different tenant. Returned results/citations are also checked by zworkforce for the expected tenant as a defense-in-depth boundary.

## Security properties

- Agent/skill `allowed_tools` policy controls whether knowledge retrieval may execute.
- Retrieval tools are classified as non-mutating.
- No service key is exposed to browser/static client code.
- No agent path directly accesses Qdrant.
- A requested tenant without its matching server-side credential is denied.
- Cross-tenant returned citations/results are rejected.
- Governed context is bounded and includes request/trace correlation.
- Administrative `knowledge:write`, `keys:admin`, and `audit:read` credentials are not required for normal zworkforce retrieval.

## Release interpretation

The consumer-side native integration is merged and the S16 implementation blocker is closed. This evidence does not by itself create or claim the final zknowbase version/tag; release metadata is produced only after the remaining zknowbase S17 documentation and release gates are green.
