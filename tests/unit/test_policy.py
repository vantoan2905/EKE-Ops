from eke_ops.modules.identity.policy import Principal, authorize


def principal(user: str, organization: str, departments: set[str]) -> Principal:
    return Principal(user, organization, "Employee", frozenset(departments), frozenset({"atlas"}))


def resource(organization: str, departments: list[str], classification: str = "internal") -> dict:
    return {
        "organization_id": organization,
        "workspace_organization_id": organization,
        "departments": departments,
        "projects": ["atlas"],
        "classification": classification,
    }


def test_atlas_department_and_tenant_isolation() -> None:
    engineer = principal("user-eng", "org-northstar", {"engineering"})
    finance = principal("user-fin", "org-northstar", {"finance"})
    other = principal("user-other", "org-harbor", {"research"})

    engineering_doc = resource("org-northstar", ["engineering"])
    finance_doc = resource("org-northstar", ["finance"], "confidential")
    assert authorize(engineer, "document:read", engineering_doc)[0]
    assert not authorize(engineer, "document:read", finance_doc)[0]
    assert authorize(finance, "document:read", finance_doc)[0]
    assert not authorize(other, "document:read", engineering_doc)[0]


def test_workspace_role_and_unknown_classification_fail_closed() -> None:
    engineer = principal("user-eng", "org-northstar", {"engineering"})
    doc = resource("org-northstar", ["engineering"])
    assert not authorize(engineer, "document:write", doc)[0]
    assert not authorize(engineer, "document:read", {**doc, "workspace_organization_id": "org-harbor"})[0]
    assert not authorize(engineer, "document:read", {**doc, "classification": "secret"})[0]
