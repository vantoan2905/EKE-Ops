"""Role and resource access rules shared by application entry points."""

from dataclasses import dataclass
from typing import Mapping, Any


ROLE_PERMISSIONS = {
    "Platform Admin": frozenset({"document:read", "document:write", "experiment:run", "trace:read"}),
    "Organization Admin": frozenset({"document:read", "document:write", "experiment:run", "trace:read"}),
    "Knowledge Manager": frozenset({"document:read", "document:write", "experiment:run"}),
    "AI Engineer": frozenset({"document:read", "experiment:run", "trace:read"}),
    "Evaluator": frozenset({"document:read", "experiment:run"}),
    "Employee": frozenset({"document:read"}),
}


@dataclass(frozen=True)
class Principal:
    user_id: str
    organization_id: str
    role: str
    departments: frozenset[str]
    projects: frozenset[str]


def authorize(principal: Principal, action: str, resource: Mapping[str, Any]) -> tuple[bool, str]:
    """Deny by default; return a stable reason suitable for an audit event."""
    if action not in ROLE_PERMISSIONS.get(principal.role, frozenset()):
        return False, "role_denied"
    if resource.get("organization_id") != principal.organization_id:
        return False, "tenant_denied"
    if resource.get("workspace_organization_id") != principal.organization_id:
        return False, "workspace_denied"
    if action == "document:read":
        classification = resource.get("classification")
        if classification not in {"internal", "confidential"}:
            return False, "classification_denied"
        departments = set(resource.get("departments") or ())
        projects = set(resource.get("projects") or ())
        if classification == "confidential" and not departments:
            return False, "classification_denied"
        if departments and not departments.intersection(principal.departments):
            return False, "department_denied"
        if projects and not projects.intersection(principal.projects):
            return False, "project_denied"
    return True, "allowed"
