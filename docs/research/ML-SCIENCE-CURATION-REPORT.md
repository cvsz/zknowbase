# ML-Science.com — Research and Knowledge Base Curation Report

- **Source:** https://www.ml-science.com/
- **Repository:** `cvsz/zknowbase`
- **Assessment date:** 2026-11-04
- **Purpose:** Identify reusable scientific and technical concepts for an enterprise AI knowledge base.
- **Assessment status:** Preliminary source assessment; not a completed page-by-page crawl.
- **Source role:** Secondary educational reference, not a normative engineering specification.

## 1. Executive decision

**KEEP AS A SECONDARY KNOWLEDGE SOURCE.**

Use the site to discover concepts and organize a learning taxonomy. Do not treat it as the sole authority for production decisions, current vendor capabilities, security controls, or research claims.

The prior high-level site review described ten broad subject groups and a collection of 200+ topic pages. Those figures are not independently verified by a complete crawl in this repository and must not be interpreted as a verified page inventory.

## 2. Curation labels

| Label | Meaning | Ingestion policy |
|---|---|---|
| `KEEP` | Reusable foundational concept with a clear technical application | Eligible after extraction, provenance capture, deduplication, and normal safety validation |
| `KEEP_WITH_VALIDATION` | Potentially useful claim or fast-changing topic | Hold for independent evidence and explicit verification |
| `REFERENCE_ONLY` | Useful index, overview, or secondary reading | Store source metadata/link; do not prioritize full-text ingestion |
| `EXCLUDE` | Duplicate, boilerplate, weakly supported, obsolete, or irrelevant content | Do not ingest |

A curation label is not a verification status. Each extracted claim must separately carry a verification status such as `UNVERIFIED`, `PARTIALLY_VERIFIED`, or `VERIFIED`.

## 3. Knowledge domains to retain

### P0 — Foundational and high-value

#### Mathematics for machine learning
- Calculus, derivatives, partial derivatives, gradients, chain rule
- Gradient descent and stochastic optimization
- Linear algebra, vectors, matrices, matrix multiplication
- Eigenvalues and eigenvectors where relevant
- Probability distributions, conditional probability, Bayes' theorem
- Entropy, cross-entropy, and information-theoretic concepts
- Statistical estimation and uncertainty

**Applications:** backpropagation, optimization, embeddings, attention, probabilistic modeling, and model evaluation.

#### Machine learning and deep learning
- Supervised, unsupervised, and reinforcement learning
- Classification, regression, clustering, and anomaly detection
- Decision trees, random forests, gradient boosting, and support vector machines
- Feature engineering and selection
- Regularization, overfitting, underfitting, and bias-variance trade-offs
- Neural networks, CNNs, RNNs, LSTMs, and Transformers
- Model training, validation, and generalization

**Applications:** model selection, prediction services, fine-tuning, evaluation, and production monitoring.

#### Foundation models and LLMs
- Tokenization and token representations
- Embeddings and positional representations
- Transformer blocks and self-attention
- Encoder, decoder, and encoder-decoder patterns
- Pretraining, instruction tuning, and alignment concepts
- Inference, context windows, decoding, and model evaluation
- Generative model families, including diffusion models

**Applications:** local inference, provider adapters, model routing, LLM applications, and model lifecycle management.

#### AI agents and multi-agent systems
- Agent architecture, state, observations, actions, and goals
- Planning, task decomposition, and decision-making
- Tool use and environment interaction
- Model-based, goal-based, utility-based, and learning-agent concepts
- Multi-agent coordination and communication
- Evaluation of agent task completion and tool correctness

**Required engineering enrichment:** explicit state machines, least-privilege tool authorization, human approval gates, execution budgets, timeouts, bounded retries, idempotency, audit trails, and failure recovery.

**Applications:** ZWorkforce, MCP services, orchestration, workflow automation, and software engineering agents.

#### Retrieval-augmented generation and knowledge systems
- Retrieval and generation architecture
- Document parsing and normalization
- Chunking and metadata design
- Dense embeddings and vector similarity
- Sparse and hybrid retrieval
- Metadata filtering and reranking
- Context assembly and citation grounding
- Retrieval and answer evaluation

**Required engineering enrichment:** tenant- and ACL-aware retrieval, prompt-injection resistance, source provenance, content hashing, deduplication, versioning, deletion propagation, and retrieval regression tests.

**Applications:** enterprise search, internal documentation assistants, and ZKnowbase.

#### Data engineering
- Data discovery, ingestion, and validation
- ETL/ELT and data pipelines
- Relational, document, graph, and vector databases
- Data warehouses, lakes, and lakehouses
- Data quality, lineage, normalization, and governance
- Batch and streaming processing

**Applications:** RAG ingestion, enterprise integration, analytics, and governed training datasets.

#### AI governance, security, and explainability
- AI risk assessment and governance
- Fairness, bias, and accountability
- Explainability and interpretability
- Privacy and data protection
- Human oversight and incident response

**Required engineering enrichment:** provenance, access control, retention, auditability, evaluation gates, model/dataset change management, and security testing.

**Applications:** enterprise AI governance and secure knowledge operations.

#### Computing systems and infrastructure
- Client-server and API architecture
- Networking and distributed computing
- Containers and orchestration
- Cloud, hybrid, and self-hosted infrastructure
- GPU computing and model serving
- Scalability, reliability, and complexity analysis

**Applications:** Docker, Kubernetes/k3s, local AI, API services, workers, and model serving.

### P1 — Retain selectively

#### Statistics and evaluation
- Descriptive statistics and distributions
- Correlation and uncertainty
- Hypothesis testing and confidence intervals
- Precision, recall, F1, confusion matrices
- A/B testing and experimental design
- Repeatability and statistical power

#### Software engineering and algorithms
- Data structures and algorithmic complexity
- Hashing, searching, sorting, and graph traversal
- Dynamic programming and greedy algorithms
- Abstraction, encapsulation, and modular design
- Error handling, testing, and maintainability

Avoid duplicating basic language tutorials already covered by authoritative language documentation.

## 4. Hold for independent validation

Classify the following as `KEEP_WITH_VALIDATION`:

- AGI, ASI, and claims about universal intelligence
- Model self-improvement and recursive self-improvement
- Deep reasoning capability claims
- AI alignment claims and proposed solutions
- Autonomous or swarm-agent capability claims
- Forecasts about future AI capabilities and industry adoption

These are research topics, not established production capabilities. Record the exact claim, date, scope, evidence, counter-evidence, and uncertainty. Prefer peer-reviewed work, original papers, reproducible experiments, and official technical documentation.

## 5. Exclude or deprioritize

- Navigation, advertisements, boilerplate, and generic search links
- Repeated introductory explanations with no additional technical value
- Vendor directories and product comparisons that are likely to become stale
- Unsupported forecasts or claims without traceable evidence
- Content unrelated to the product's knowledge domains
- Duplicate examples that do not improve retrieval or understanding

## 6. Source quality and licensing

The source is a secondary educational website. Its explanations can be useful for orientation, but claims that affect architecture, security, model behavior, or production operations require independent validation.

The website has been described as identifying a CC BY 4.0 license. This assessment has not independently audited every page or embedded asset. Before copying or adapting source text, verify the current license statement and review third-party figures, images, papers, and embedded materials separately.

Where reuse is permitted, retain author attribution, original title, source URL, license identifier, retrieval date, and modification notice. Prefer original summaries and normalized technical notes over wholesale reproduction.

## 7. Recommended metadata contract

Every extracted knowledge document should include at least:

```yaml
---
title: "Concept title"
domain: "machine-learning"
topic: "concept-slug"
source:
  name: "The Science of Machine Learning & AI"
  url: "https://www.ml-science.com/"
  original_url: ""
  author: ""
  source_type: "secondary"
  license: "UNVERIFIED"
provenance:
  retrieved_at: "2026-11-04"
  content_sha256: ""
quality:
  classification: "KEEP"
  verification_status: "UNVERIFIED"
  confidence: "NOT_ASSESSED"
knowledge:
  content_type: "technical-concept"
  tags: []
  related_topics: []
  prerequisites: []
maintenance:
  last_reviewed: "2026-11-04"
  review_required: true
---
```

Do not invent page URLs, authors, dates, license coverage, confidence scores, or verification status. Use the actual page-level values discovered during extraction.

## 8. Integration with the existing ZKnowbase architecture

The current platform already provides:
- FastAPI ingestion and query APIs
- PDF, Markdown, and TXT ingestion
- URL ingestion with SSRF guardrails
- durable asynchronous ingestion queue and worker
- SQLite metadata with optional local PostgreSQL
- Qdrant vector retrieval
- Ollama embeddings and local generation
- grounded answers with source/chunk citations
- scoped service API keys and audit events

Therefore this research pack does **not** propose a second ingestion engine, vector store, model provider, or queue.

Use the existing authenticated ingestion API and existing security validation. Do not write directly to Qdrant or bypass the ingestion worker. Use a read-only scoped key for retrieval-only consumers. Preserve tenant isolation and deletion semantics.

Potential future work, subject to implementation audit:
- a source registry and crawl manifest
- bounded, allowlisted page discovery
- content hashing and source-version tracking
- HTML-to-Markdown extraction with boilerplate removal
- page-level attribution and license metadata
- deterministic classification and deduplication
- import preview and dry-run report
- retrieval evaluation cases for technical concepts

Do not implement a crawler or new API contract until current parsers, URL ingestion, queue, tenant boundaries, and tests have been reviewed.

## 9. Acceptance criteria for a future full extraction

- Every retained page has an exact canonical URL and retrieval timestamp.
- Every document has author/license metadata where actually available.
- Every extracted document is deduplicated by normalized content hash.
- Every claim has an explicit verification state.
- High-impact claims have independent primary evidence.
- Third-party assets are reviewed separately.
- Source instructions are treated as untrusted content.
- Ingestion uses the existing authenticated API and security controls.
- Tenant isolation and source deletion behavior are tested.
- Retrieval quality and citation hit rate are evaluated before release.

## 10. Status

| Work item | Status |
|---|---|
| High-level source assessment | Preliminary |
| Knowledge domain taxonomy | Curated |
| KEEP / validation / exclusion policy | Defined |
| Source manifest | Registered; page inventory incomplete |
| Full page-by-page crawl | Not completed |
| Primary-source claim validation | Not completed |
| Source content ingestion into ZKnowbase | Not performed |
| Retrieval evaluation for this pack | Not performed |

**Conclusion:** retain ML-Science.com as a secondary discovery and foundational-learning source. Only ingest page-level material after provenance capture, quality classification, deduplication, and the applicable verification gates.
