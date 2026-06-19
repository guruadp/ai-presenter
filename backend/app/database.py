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
    engine = _get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_project_slide_columns(engine)


def _ensure_sqlite_project_slide_columns(engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "project_slides" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("project_slides")}
    statements = []
    if "vision_summary" not in columns:
        statements.append("ALTER TABLE project_slides ADD COLUMN vision_summary TEXT NOT NULL DEFAULT ''")
    if "generation_context" not in columns:
        statements.append("ALTER TABLE project_slides ADD COLUMN generation_context JSON NOT NULL DEFAULT '{}'")

    if statements:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))


def get_db() -> Generator[Session, None, None]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine())
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
