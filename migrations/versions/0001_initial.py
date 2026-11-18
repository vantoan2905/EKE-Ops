"""Create the initial demo-compatible schema.

Revision ID: 0001_initial
Revises:
"""

from pathlib import Path

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path(__file__).with_suffix(".sql").read_text()
    connection = op.get_bind()
    for statement in sql.split(";"):
        if statement.strip():
            connection.exec_driver_sql(statement)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS eke_demo CASCADE")
