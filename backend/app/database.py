from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_engine = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


def _get_engine():
    global _engine
    if _engine is None:
        from app.config import get_settings
        s = get_settings()
        _engine = create_engine(s.DATABASE_URL, connect_args={"check_same_thread": False})
    return _engine


def init_db() -> None:
    from app.models import knowledge_base as _  # noqa: F401 — registers ORM models
    from app.models import project as _project  # noqa: F401 — registers ORM models
    Base.metadata.create_all(bind=_get_engine())


def get_db() -> Generator[Session, None, None]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine())
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
