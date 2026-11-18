"""Persist decisions without storing document text."""

from sqlalchemy import text

from eke_ops.infrastructure.db.session import engine
from eke_ops.modules.identity.policy import Principal


def record_decision(
    principal: Principal, action: str, resource_type: str, resource_id: str | None,
    allowed: bool, reason: str,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO eke_demo.audit_events
                    (user_id, organization_id, action, resource_type, resource_id, allowed, reason)
                VALUES (:user_id, :organization_id, :action, :resource_type, :resource_id, :allowed, :reason)
            """),
            {
                "user_id": principal.user_id,
                "organization_id": principal.organization_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "allowed": allowed,
                "reason": reason,
            },
        )
