# Enterprise Knowledge EvalOps — Architecture & Flows

## Recommended architecture

**Modular Monolith + Hexagonal Architecture (Ports & Adapters) + Event-Driven Background Workers**, with a separate MCP server, LangGraph agent, and centralized RBAC/ABAC authorization.

## 1. High-level system architecture

```mermaid
flowchart TB
    UI[Next.js Dashboard] --> API[FastAPI REST / SSE API]
    API --> AUTH[Authentication and Authorization]
    AUTH --> APP[Application Services]
    subgraph CORE[Modular Monolith]
        APP --> KM[Knowledge Management]
        APP --> RET[Retrieval Engine]
        APP --> EVAL[Evaluation Engine]
        APP --> EXP[Experiment Management]
        APP --> AGENT[LangGraph Agent]
        APP --> OBS[Observability]
        RET --> PORT[Retriever Port]
        PORT --> DENSE[Dense Adapter]
        PORT --> HYBRID[Hybrid Adapter]
        PORT --> GRAPH[Graph Adapter]
        AGENT --> MC[MCP Client]
    end
    MC --> MCP[MCP Server - Separate Process]
    MCP --> POLICY[RBAC / ABAC Enforcement]
    API --> QUEUE[Redis / Celery]
    QUEUE --> WORKER[Background Workers]
    WORKER --> KM
    WORKER --> EXP
    DENSE --> Q[(Qdrant)]
    HYBRID --> Q
    HYBRID --> BM[(BM25 Index)]
    GRAPH --> N[(Neo4j)]
    APP --> PG[(PostgreSQL)]
    OBS --> LF[Langfuse]
    AGENT --> LLM[LLM Provider]
```

## 2. Hexagonal retrieval flow

```mermaid
flowchart LR
    API[REST API] --> UC[Retrieval Use Case]
    AG[LangGraph Agent] --> UC
    MCP[MCP Tool Handler] --> UC
    UC --> P[Retriever Port]
    P --> D[Dense Adapter]
    P --> H[Hybrid Adapter]
    P --> G[Graph Adapter]
    D --> Q[(Qdrant)]
    H --> B[(BM25 + Qdrant)]
    G --> N[(Neo4j)]
```

## 3. RBAC + ABAC authorization flow

```mermaid
flowchart TD
    U[User] --> IDP[Keycloak / OIDC]
    IDP --> API[FastAPI]
    API --> PEP[Policy Enforcement Point]
    PEP --> PDP[Policy Decision Point]
    PDP --> RBAC[Role Permissions]
    PDP --> ABAC[User and Resource Attributes]
    RBAC --> DEC{Allow?}
    ABAC --> DEC
    DEC -->|No| DENY[403 / Audit]
    DEC -->|Yes| SEARCH[Authorized Retrieval]
    SEARCH --> LLM[LLM Context]
```

Authorization must be enforced at API, MCP tool, search/index, graph traversal, document access, and trace visibility boundaries. Never trust identity attributes supplied by an LLM.

## 4. Background job flow

```mermaid
flowchart LR
    A[API Request] --> B[Create Job in PostgreSQL]
    B --> C[Celery Queue]
    C --> D[Worker]
    D --> E[Update Job State]
    E --> F[(PostgreSQL)]
    F --> G[Dashboard Polling / SSE]
```

## 5. MCP agent flow

```mermaid
flowchart TD
    A[Question] --> B[LangGraph Planner]
    B --> C{Choose Tool}
    C --> D[MCP Dense / Hybrid Search]
    C --> E[MCP Graph Search]
    C --> F[MCP Document Access]
    D --> P[Authorization Check]
    E --> P
    F --> P
    P --> G[Collect Authorized Evidence]
    G --> H{Enough Evidence?}
    H -->|No - within budget| B
    H -->|Yes| I[Generate Cited Answer]
    H -->|Budget exhausted| J[Abstain]
    I --> K[Trace and Evaluate]
    J --> K
```

## 6. Deployment units

| Unit | Purpose |
|---|---|
| Next.js | Dashboard |
| FastAPI | Modular monolith API |
| Celery worker | Ingestion and evaluation jobs |
| MCP server | Authenticated retrieval tools |
| PostgreSQL | Transactional data and evaluation results |
| Qdrant | Dense vector index |
| BM25 index | Sparse search |
| Neo4j | Knowledge graph |
| Redis | Broker and optional cache |
| Keycloak / OIDC | Authentication |
| Cerbos or OPA | Authorization policy decisions |
| Langfuse / OpenTelemetry | Tracing and observability |

## 7. Module boundaries

- Identity & Access: tenant membership, RBAC, ABAC, policies, audit.
- Knowledge: documents, ingestion, chunking, indexing, versioning.
- Retrieval: Dense, Hybrid, GraphRAG through shared ports.
- Agents & MCP: LangGraph orchestration and secured MCP tool integration.
- Evaluation: datasets, retrieval and answer metrics, tool-use scoring.
- Experiments: configurations, jobs, runs, comparison, regression tests.
- Observability: traces, tokens, cost, latency, errors.

## 8. Implementation order

1. Identity, tenant isolation, RBAC/ABAC.
2. Document ingestion and Dense/Hybrid retrieval.
3. Evaluation datasets, experiment runner, and metrics.
4. GraphRAG and permission-aware graph traversal.
5. MCP server and LangGraph agent.
6. Tracing, dashboard, regression tests, Docker deployment.

## 9. Architecture decisions

- ADR-001: Modular monolith over microservices.
- ADR-002: Hexagonal retrieval adapters.
- ADR-003: Centralized RBAC + ABAC policy engine.
- ADR-004: MCP for tool interoperability.
- ADR-005: Celery for asynchronous workloads.
- ADR-006: PostgreSQL as source of truth.
- ADR-007: Qdrant and Neo4j as specialized indexes.
- ADR-008: Langfuse + OpenTelemetry for observability.
