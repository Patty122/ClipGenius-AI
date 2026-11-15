from __future__ import annotations
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from ..config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def init_db():
    global _engine, _Session
    s = get_settings()
    _engine = create_engine(s.db_url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(_engine, "connect")
    def _pragmas(dbapi, _):
        cur = dbapi.cursor(); cur.execute("PRAGMA foreign_keys=ON"); cur.execute("PRAGMA journal_mode=WAL"); cur.close()

    from .. import models  # noqa: F401  (register tables)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_db():
    if _Session is None:
        init_db()
    db = _Session()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    if _Session is None:
        init_db()
    db = _Session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
