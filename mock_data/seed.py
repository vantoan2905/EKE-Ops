"""Print PostgreSQL upserts for the synthetic demo fixture.

Usage: python mock_data/seed.py | psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL"
"""

import json
from pathlib import Path


def sql_value(value: object) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, list):
        return "ARRAY[" + ", ".join(sql_value(item) for item in value) + "]::text[]"
    if isinstance(value, int):
        return str(value)
    raise TypeError(f"Unsupported fixture value: {value!r}")


def upsert(table: str, row: dict[str, object], key: tuple[str, ...] = ("id",)) -> str:
    columns = list(row)
    values = ", ".join(sql_value(row[column]) for column in columns)
    assignments = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in columns if column not in key
    )
    return (
        f"INSERT INTO eke_demo.{table} ({', '.join(columns)}) VALUES ({values}) "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {assignments};"
    )


def main() -> None:
    fixture = json.loads(Path(__file__).with_name("demo.json").read_text())
    statements = ["BEGIN;"]
    for table in ("organizations", "workspaces", "users"):
        statements.extend(upsert(table, row) for row in fixture[table])

    for document in fixture["documents"]:
        chunks = document["chunks"]
        statements.append(upsert("documents", {k: v for k, v in document.items() if k != "chunks"}))
        statements.extend(
            upsert("document_chunks", {**chunk, "document_id": document["id"]})
            for chunk in chunks
        )

    dataset = fixture["evaluation_dataset"]
    statements.append(upsert("evaluation_datasets", {k: v for k, v in dataset.items() if k != "cases"}))
    statements.extend(
        upsert("evaluation_cases", {**case, "dataset_id": dataset["id"]})
        for case in dataset["cases"]
    )

    experiment = fixture["experiment"]
    statements.append(upsert("experiments", {k: experiment[k] for k in ("id", "dataset_id", "dataset_version")}))
    statements.extend(
        upsert("experiment_configurations", {**config, "experiment_id": experiment["id"]})
        for config in experiment["configurations"]
    )
    run = experiment["example_run"]
    statements.append(upsert("experiment_runs", {**{k: run[k] for k in ("id", "configuration_id", "status", "evaluator_version")}, "experiment_id": experiment["id"]}))
    statements.extend(
        upsert("experiment_results", {**result, "run_id": run["id"]}, key=("run_id", "case_id"))
        for result in run["results"]
    )
    statements.append("COMMIT;")
    print("\n".join(statements))


if __name__ == "__main__":
    main()
