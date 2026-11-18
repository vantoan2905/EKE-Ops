"""Explicit local fixture identity, disabled unless ENABLE_DEMO_AUTH=true."""

from typing import Annotated

from fastapi import Header, HTTPException
from sqlalchemy import text

from eke_ops.core.config import settings
from eke_ops.infrastructure.db.session import engine
from eke_ops.modules.identity.policy import Principal


def get_demo_principal(x_demo_user: Annotated[str | None, Header()] = None) -> Principal:
    if not settings.enable_demo_auth:
        raise HTTPException(status_code=503, detail="authentication is not configured")
    if not x_demo_user:
        raise HTTPException(status_code=401, detail="X-Demo-User header required")
    with engine.connect() as connection:
        user = connection.execute(
            text("SELECT * FROM eke_demo.users WHERE id = :user_id"),
            {"user_id": x_demo_user},
        ).mappings().first()
    if user is None:
        raise HTTPException(status_code=401, detail="unknown demo user")
    return Principal(
        user_id=user["id"],
        organization_id=user["organization_id"],
        role=user["role"],
        departments=frozenset(user["departments"]),
        projects=frozenset(user["projects"]),
    )
