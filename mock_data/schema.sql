CREATE SCHEMA IF NOT EXISTS eke_demo;

CREATE TABLE IF NOT EXISTS eke_demo.organizations (
    id text PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE IF NOT EXISTS eke_demo.workspaces (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES eke_demo.organizations(id),
    name text NOT NULL
);

CREATE TABLE IF NOT EXISTS eke_demo.users (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES eke_demo.organizations(id),
    name text NOT NULL,
    role text NOT NULL,
    departments text[] NOT NULL DEFAULT '{}',
    projects text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS eke_demo.documents (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES eke_demo.organizations(id),
    workspace_id text NOT NULL REFERENCES eke_demo.workspaces(id),
    title text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    owner_user_id text NOT NULL REFERENCES eke_demo.users(id),
    classification text NOT NULL,
    departments text[] NOT NULL DEFAULT '{}',
    projects text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS eke_demo.document_chunks (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES eke_demo.documents(id),
    text text NOT NULL
);

CREATE TABLE IF NOT EXISTS eke_demo.evaluation_datasets (
    id text PRIMARY KEY,
    version integer NOT NULL CHECK (version > 0),
    organization_id text NOT NULL REFERENCES eke_demo.organizations(id)
);

CREATE TABLE IF NOT EXISTS eke_demo.evaluation_cases (
    id text PRIMARY KEY,
    dataset_id text NOT NULL REFERENCES eke_demo.evaluation_datasets(id),
    user_id text NOT NULL REFERENCES eke_demo.users(id),
    question text NOT NULL,
    authorized_relevant_chunk_ids text[] NOT NULL DEFAULT '{}',
    expected_answer text NOT NULL,
    expected_citation_chunk_ids text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS eke_demo.experiments (
    id text PRIMARY KEY,
    dataset_id text NOT NULL REFERENCES eke_demo.evaluation_datasets(id),
    dataset_version integer NOT NULL CHECK (dataset_version > 0)
);

CREATE TABLE IF NOT EXISTS eke_demo.experiment_configurations (
    id text PRIMARY KEY,
    experiment_id text NOT NULL REFERENCES eke_demo.experiments(id),
    retriever text NOT NULL,
    top_k integer NOT NULL CHECK (top_k > 0)
);

CREATE TABLE IF NOT EXISTS eke_demo.experiment_runs (
    id text PRIMARY KEY,
    experiment_id text NOT NULL REFERENCES eke_demo.experiments(id),
    configuration_id text NOT NULL REFERENCES eke_demo.experiment_configurations(id),
    status text NOT NULL,
    evaluator_version text NOT NULL
);

CREATE TABLE IF NOT EXISTS eke_demo.experiment_results (
    run_id text NOT NULL REFERENCES eke_demo.experiment_runs(id),
    case_id text NOT NULL REFERENCES eke_demo.evaluation_cases(id),
    retrieved_chunk_ids text[] NOT NULL DEFAULT '{}',
    answer_citation_chunk_ids text[] NOT NULL DEFAULT '{}',
    latency_ms integer NOT NULL CHECK (latency_ms >= 0),
    input_tokens integer NOT NULL CHECK (input_tokens >= 0),
    output_tokens integer NOT NULL CHECK (output_tokens >= 0),
    PRIMARY KEY (run_id, case_id)
);

-- Demo query only: resolve the user from trusted application identity before
-- filtering. Direct table access is not an authorization boundary.
CREATE OR REPLACE VIEW eke_demo.authorized_chunks AS
SELECT u.id AS user_id, c.id AS chunk_id, c.document_id, c.text
FROM eke_demo.users AS u
JOIN eke_demo.documents AS d
  ON d.organization_id = u.organization_id
 AND (cardinality(d.projects) = 0 OR d.projects && u.projects)
 AND (cardinality(d.departments) = 0 OR d.departments && u.departments)
JOIN eke_demo.document_chunks AS c ON c.document_id = d.id;
