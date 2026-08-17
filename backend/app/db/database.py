import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import resolved_database_url

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_url = resolved_database_url()
_connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}
engine = create_engine(_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from app.db import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)
    _run_lightweight_migrations()


# Columns added after the first release. No Alembic in this hackathon build, so we
# add missing columns idempotently on startup (create_all never ALTERs existing tables).
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "risks": {
        "review_status": "VARCHAR(16) DEFAULT 'pending'",
        "reviewer_note": "TEXT",
    },
}


def _run_lightweight_migrations() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue  # create_all just made it with the full schema
            have = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    log.info("migration: added %s.%s", table, name)
