from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "tracker.sqlite3"
DATABASE_URL = os.getenv("INVESTMENT_TRACKER_DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")


class Base(DeclarativeBase):
    pass


def _connect_args(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
            sqlite_path = Path(database_url.removeprefix("sqlite:///"))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return {"check_same_thread": False}
    return {}


engine = create_engine(DATABASE_URL, connect_args=_connect_args(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def initialize_database() -> None:
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        create_db_and_tables()
        return

    alembic_ini = BACKEND_ROOT / "alembic.ini"
    if not alembic_ini.exists():
        create_db_and_tables()
        return

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    if _needs_legacy_baseline_stamp():
        create_db_and_tables()
        command.stamp(config, "head")
        return

    command.upgrade(config, "head")


def create_db_and_tables() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def _needs_legacy_baseline_stamp() -> bool:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    app_tables = {
        "accounts",
        "import_sessions",
        "market_prices",
        "portfolios",
        "transaction_fingerprints",
        "transactions",
    }
    return bool(table_names & app_tables) and "alembic_version" not in table_names


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
