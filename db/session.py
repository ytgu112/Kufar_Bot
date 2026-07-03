from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base


def _sqlite_url(db_path: str) -> str:
    if db_path == ":memory:":
        return "sqlite+pysqlite:///:memory:"

    path = Path(db_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+pysqlite:///{path.as_posix()}"


def create_engine_for_db(db_path: str) -> Engine:
    return create_engine(
        _sqlite_url(db_path),
        connect_args={"check_same_thread": False},
        future=True,
    )


def create_session_factory(db_path: str) -> sessionmaker[Session]:
    engine = create_engine_for_db(db_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

