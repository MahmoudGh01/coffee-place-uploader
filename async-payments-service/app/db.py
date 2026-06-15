from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


def _engine_for(database_url: str):
    if database_url.startswith("sqlite+pysqlite:///:memory:"):
        return create_engine(
            database_url,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            future=True,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url, future=True)


engine = _engine_for(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def rebind_engine(database_url: str) -> None:
    global engine
    global SessionLocal
    engine = _engine_for(database_url)
    SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
