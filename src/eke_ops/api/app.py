"""HTTP entry point for EKE Ops."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from eke_ops.infrastructure.db.session import engine
from eke_ops.infrastructure.auth.demo import get_demo_principal
from eke_ops.modules.identity.audit import record_decision
from eke_ops.modules.identity.policy import Principal, authorize

class HealthResponse(BaseModel):
    status: str
    database: str


app = FastAPI(
    title="EKE Ops API",
    description=(
        "Enterprise Knowledge EvalOps API. Phase 1 document reads use a local "
        "demo identity header and enforce organization, workspace, department, "
        "project, and classification rules. Set ENABLE_DEMO_AUTH=true for local use."
    ),
    version="0.1.0",
    swagger_ui_parameters={"docExpansion": "list", "displayRequestDuration": True, "filter": True},
)


@app.get("/", include_in_schema=False)
def swagger_home() -> RedirectResponse:
    """Open the interactive API documentation from the root URL."""
    return RedirectResponse(url="/docs")


@app.get(
    "/health",
    tags=["System"],
    summary="Check API and database health",
    response_model=HealthResponse,
    responses={503: {"description": "PostgreSQL is unavailable"}},
)
def health() -> HealthResponse:
    """Return healthy only when PostgreSQL accepts a query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return HealthResponse(status="ok", database="ok")


PrincipalDep = Annotated[Principal, Depends(get_demo_principal)]


@app.get("/documents", tags=["Documents"], summary="List documents accessible to the demo user")
def list_documents(principal: PrincipalDep) -> list[dict]:
    permitted, reason = authorize(principal, "document:read", {
        "organization_id": principal.organization_id,
        "workspace_organization_id": principal.organization_id,
        "classification": "internal",
    })
    if not permitted:
        record_decision(principal, "document:read", "document_list", None, False, reason)
        raise HTTPException(status_code=403, detail="document listing denied")
    with engine.connect() as connection:
        documents = connection.execute(
            text("""
                SELECT d.id, d.title, d.version, d.classification, d.organization_id,
                       d.departments, d.projects, w.organization_id AS workspace_organization_id
                FROM eke_demo.documents AS d
                JOIN eke_demo.workspaces AS w ON w.id = d.workspace_id
                WHERE d.organization_id = :organization_id
                ORDER BY d.id
            """),
            {"organization_id": principal.organization_id},
        ).mappings().all()
    visible = [
        {"id": doc["id"], "title": doc["title"], "version": doc["version"],
         "classification": doc["classification"]}
        for doc in documents if authorize(principal, "document:read", doc)[0]
    ]
    record_decision(principal, "document:read", "document_list", None, True, "filtered")
    return visible


@app.get("/documents/{document_id}", tags=["Documents"], summary="Read an authorized document")
def read_document(document_id: str, principal: PrincipalDep) -> dict:
    with engine.connect() as connection:
        document = connection.execute(
            text("""
                SELECT d.id, d.title, d.version, d.classification, d.organization_id,
                       d.departments, d.projects, w.organization_id AS workspace_organization_id
                FROM eke_demo.documents AS d
                JOIN eke_demo.workspaces AS w ON w.id = d.workspace_id
                WHERE d.id = :document_id
            """),
            {"document_id": document_id},
        ).mappings().first()
        if document is None:
            raise HTTPException(status_code=404, detail="document not found")
        allowed, reason = authorize(principal, "document:read", document)
        if allowed:
            chunks = connection.execute(
                text("SELECT id, text FROM eke_demo.document_chunks WHERE document_id = :document_id ORDER BY id"),
                {"document_id": document_id},
            ).mappings().all()
    record_decision(principal, "document:read", "document", document_id, allowed, reason)
    if not allowed:
        raise HTTPException(status_code=404, detail="document not found")
    return {
        "id": document["id"], "title": document["title"], "version": document["version"],
        "classification": document["classification"], "chunks": [dict(chunk) for chunk in chunks],
    }
