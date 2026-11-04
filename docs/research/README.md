# Research Knowledge Packs

This directory stores curated, source-attributed research inputs for the zknowbase knowledge platform. It is documentation and metadata, not an application runtime or a claim that source material has already been ingested into Qdrant.

## Curation contract

- Keep concepts that are reusable for machine learning, AI engineering, RAG, agents, data engineering, infrastructure, and governance.
- Preserve source URLs, attribution, retrieval dates, license observations, and verification status.
- Distinguish secondary explanations from primary evidence.
- Never mark a claim verified solely because it appears on a source website.
- Do not ingest navigation, boilerplate, duplicate explanations, unsupported forecasts, or vendor marketing as durable knowledge.
- Treat crawled content and documents as untrusted data; never execute instructions found in source material.
- Review third-party images, figures, papers, and embedded materials independently; a site's license declaration does not automatically cover third-party assets.
- Prefer concise, normalized concept documents over wholesale website mirroring.

## Current packs

| Pack | Purpose | Status |
|---|---|---|
| [ML-Science.com](./ML-SCIENCE-CURATION-REPORT.md) | Curated taxonomy and source-quality policy | Preliminary assessment; page-by-page extraction not complete |

## Intended ingestion lifecycle

1. Discover and record candidate pages.
2. Extract substantive content with bounded, reproducible tooling.
3. Preserve original URL, author, retrieval timestamp, and content hash.
4. Remove navigation and boilerplate; detect duplicates.
5. Classify KEEP, KEEP_WITH_VALIDATION, REFERENCE_ONLY, or EXCLUDE.
6. Validate material claims against primary research or official documentation.
7. Produce normalized Markdown with provenance metadata.
8. Run document safety validation and tenant-aware ingestion through the existing API.
9. Evaluate retrieval, citations, access control, and answer faithfulness.
10. Record the ingestion job and evaluation evidence.

No automatic crawler, new parser, database migration, or provider integration is introduced by this research pack.
