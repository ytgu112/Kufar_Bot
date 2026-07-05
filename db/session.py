from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base

_engine: Engine | None = None


def _sqlite_url(db_path: str) -> str:
    if db_path == ":memory:":
        return "sqlite+pysqlite:///:memory:"

    path = Path(db_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+pysqlite:///{path.as_posix()}"


def create_engine_for_db(db_path: str) -> Engine:
    global _engine
    engine = create_engine(
        _sqlite_url(db_path),
        connect_args={"check_same_thread": False, "timeout": 10},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _engine = engine
    return engine


def create_session_factory(db_path: str) -> sessionmaker[Session]:
    engine = create_engine_for_db(db_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def dispose_engine() -> None:
    if _engine is not None:
        _engine.dispose()

