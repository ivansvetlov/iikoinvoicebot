"""Инициализация подключения к базе данных."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def _build_engine():
    url = settings.database_url
    if not url:
        return None
    if url.startswith("sqlite:///./"):
        base = Path(__file__).resolve().parent.parent
        db_path = url.replace("sqlite:///./", "", 1)
        url = f"sqlite:///{(base / db_path).as_posix()}"
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


_engine = _build_engine()
SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False) if _engine else None
_initialized = False


def init_db() -> None:
    """Создает таблицы при первом запуске."""
    global _initialized
    if _initialized or _engine is None:
        return
    if settings.database_url.startswith("sqlite"):
        from pathlib import Path

        db_path = settings.database_url.replace("sqlite:///", "", 1)
        if db_path:
            Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    from app.models import Base

    Base.metadata.create_all(bind=_engine)
    _initialized = True


@contextmanager
def get_session():
    if SessionLocal is None:
        yield None
        return
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
