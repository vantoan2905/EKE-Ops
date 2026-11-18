# EKE Ops implementation plan

## Goal

Build a reproducible demo that ingests enterprise documents, answers questions from evidence each user may access, and compares retrieval and answer quality across configurations. The first release should make tenant isolation and access decisions visible in tests, citations, audit records, and experiment results.

This plan builds on [README.md](README.md), [architecture.md](architecture.md), and the synthetic fixture in [mock_data/demo.json](mock_data/demo.json). The repository is currently a scaffold: its Python modules are empty and `uv run eke-ops` prints a placeholder message.

## Guiding decisions

- Keep one FastAPI application with feature modules under `src/eke_ops/modules/`. Run MCP and background workers as separate processes that call the same application services.
- PostgreSQL is the source of truth for users, documents, versions, datasets, runs, and audit events. Qdrant and other search indexes are rebuildable projections.
- Resolve user and tenant from verified identity. Apply role permissions and resource rules before text enters search results, model context, citations, traces, or exports. Direct calls to MCP tools must use the same checks.
- Keep retrieval behind a small `Retriever` interface so keyword, dense, and hybrid implementations can be compared with the same input and output types.
- Use the eight demo evaluation cases as the first executable acceptance suite. Add larger generated data only after the small suite passes.

## Phase 0 — Make the project runnable (implemented)

**Build**

1. Add FastAPI, database access, migrations, test tooling, configuration, and an `.env.example` to `pyproject.toml` and the repository.
2. Add local service startup for PostgreSQL. Add Qdrant and Redis when the phases that use them begin.
3. Turn `mock_data/schema.sql` into versioned application migrations. Keep the seed script as development data, not the production migration path.
4. Add `GET /health` and a documented command to start the API.

**Done when:** a fresh checkout can start PostgreSQL, apply migrations, load the demo fixture, start the API, and receive a healthy response using README commands.

## Phase 1 — Identity and authorization (in progress)

**Build**

1. Define a request principal with user ID, organization ID, roles, departments, and projects. In local development, use an explicit test identity mechanism; before deployment, validate OIDC tokens and map claims to server-owned membership records.
2. Implement `authorize(principal, action, resource)` in `modules/identity/`. Define role permissions for document reads, ingestion, evaluation, experiment runs, and trace access.
3. Enforce tenant, workspace, project, department, and classification rules on document and chunk reads. Write allow and deny audit events.
4. Add database constraints or service checks that prevent a document, workspace, owner, case, or experiment from referring across organizations.
5. Review the demo `authorized_chunks` view: it checks tenant, project, and department, but it does not enforce classification or role permissions. The application policy must cover those before the view is used as a retrieval source.

**Done when:** the same Atlas question yields different readable evidence for `user-eng`, `user-fin`, `user-cross`, and `user-other`; forbidden reads and cross-tenant IDs are denied and audited.

## Phase 2 — Knowledge ingestion and retrieval

**Build**

1. Add document create/upload, metadata validation, versioning, parsing, and deterministic chunk IDs. Re-ingestion should replace or supersede old indexed chunks without duplicates.
2. Define `SearchRequest` (trusted principal, query, top K, filters) and `SearchHit` (chunk ID, document/version ID, score, citation metadata) in `modules/retrieval/ports/`.
3. Implement a PostgreSQL keyword search adapter first. Make `POST /search` return ranked, authorized hits. Check authorization before returning text and again before document fetches.
4. Add an embedding pipeline and Qdrant dense adapter. Store tenant and access metadata in index payloads, use indexed filters during candidate retrieval, and recheck candidates against the source-of-truth policy before returning them.
5. Add BM25 plus dense fusion as the hybrid adapter. Keep scoring details and retriever version in the result metadata.

**Done when:** keyword, dense, and hybrid search use the same API; all returned hits have stable citations; re-ingestion is idempotent; forbidden chunks never appear in results, even when they match the query best.

## Phase 3 — Evaluation and experiments

**Build**

1. Store immutable dataset versions and validate every case's user, expected evidence, and expected citations.
2. Implement an experiment runner that records dataset version, retriever configuration, code/evaluator version, case outputs, latency, token usage, and errors. Run larger jobs in a worker; keep a small synchronous runner for development.
3. Calculate Recall@K, MRR, and nDCG against each case's **authorized relevant evidence**. Add citation precision and a check that flags any retrieved or cited chunk outside the user's access set.
4. Provide `POST /experiments`, `POST /experiments/{id}/runs`, `GET /runs/{id}`, and `GET /runs/{id}/results` or equivalent endpoints.

**Done when:** one command runs all eight demo cases for dense and hybrid configurations, saves repeatable results, and reports both quality metrics and access violations. The `user-other` case expects no authorized evidence.

## Phase 4 — Cited answers, MCP, and agent

**Build**

1. Add a basic answer service that uses only authorized `SearchHit` text, produces citations by chunk ID, and abstains when evidence is insufficient.
2. Expose search and document-read operations through an MCP server. Authenticate every tool request and call the same authorization and retrieval services as the API.
3. Add a LangGraph agent with a small tool budget, explicit termination, cited output, and abstention. Treat retrieved documents and tool output as untrusted instructions.
4. Extend evaluation to answer correctness, faithfulness, citation validity, latency, and cost. Record prompt/model/evaluator versions with each run.

**Done when:** direct API calls, direct MCP calls, and agent calls give the same user the same accessible evidence; the agent cannot cite forbidden chunks or invent a citation.

## Phase 5 — Dashboard, observability, and release

**Build**

1. Add background ingestion/evaluation jobs with durable status in PostgreSQL and a Redis-backed queue. Expose status through polling or SSE.
2. Record traces, errors, token use, latency, and audit events. Enforce read permissions on traces and redact restricted content where appropriate.
3. Build a Next.js dashboard for datasets, experiments, per-case results, access failures, and comparisons across retrieval configurations.
4. Add integration tests for cross-tenant access, index filter mistakes, MCP tool calls, prompt injection, and trace visibility. Document local deployment and the exact demo sequence.

**Done when:** a reviewer can start the stack from a fresh checkout, reproduce the cross-functional Atlas demo, compare two runs in the UI, and inspect why a result was allowed or denied.

## Later extension — Graph retrieval

Add Neo4j and a graph retriever only after the first release works. Every node and edge traversal must preserve document provenance and enforce the same access policy before returning graph evidence. Compare graph retrieval using the existing dataset and experiment runner.

## First implementation slice

Build this slice before adding an LLM or dashboard:

1. Start PostgreSQL and load the demo fixture.
2. Add the API and trusted local test principals for the four Atlas users.
3. Add one authorized keyword-search endpoint over demo chunks.
4. Add integration tests showing the four users receive their expected accessible chunk IDs and no cross-tenant chunks.
5. Add a simple retrieval evaluation command that runs the eight fixture cases and prints Recall@K plus access violations.

This slice validates the data model, policy, search boundary, and evaluation loop before adding more services.
