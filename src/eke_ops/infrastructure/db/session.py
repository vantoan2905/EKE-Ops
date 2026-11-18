"""PostgreSQL engine used by the API."""

from sqlalchemy import create_engine

from eke_ops.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
