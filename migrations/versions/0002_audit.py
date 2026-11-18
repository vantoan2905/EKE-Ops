"""Record authorization decisions.

Revision ID: 0002_audit
Revises: 0001_initial
"""

from alembic import op

revision = "0002_audit"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE eke_demo.audit_events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            user_id text NOT NULL REFERENCES eke_demo.users(id),
            organization_id text NOT NULL REFERENCES eke_demo.organizations(id),
            action text NOT NULL,
            resource_type text NOT NULL,
            resource_id text,
            allowed boolean NOT NULL,
            reason text NOT NULL
        )
    """)
    op.execute("CREATE INDEX audit_events_org_time ON eke_demo.audit_events (organization_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE eke_demo.audit_events")
