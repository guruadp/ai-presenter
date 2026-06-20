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
    _ensure_sqlite_project_slide_script_columns(engine)
    _ensure_sqlite_epic12_columns(engine)


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


def _ensure_sqlite_project_slide_script_columns(engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "project_slide_scripts" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("project_slide_scripts")}
    statements = []
    if "revision_history" not in columns:
        statements.append("ALTER TABLE project_slide_scripts ADD COLUMN revision_history JSON NOT NULL DEFAULT '[]'")
    if "tone_override" not in columns:
        statements.append("ALTER TABLE project_slide_scripts ADD COLUMN tone_override JSON NOT NULL DEFAULT '{}'")
    if "preview_config" not in columns:
        statements.append("ALTER TABLE project_slide_scripts ADD COLUMN preview_config JSON NOT NULL DEFAULT '{}'")
    if "stale_reasons" not in columns:
        statements.append("ALTER TABLE project_slide_scripts ADD COLUMN stale_reasons JSON NOT NULL DEFAULT '[]'")
    if "approved_at" not in columns:
        statements.append("ALTER TABLE project_slide_scripts ADD COLUMN approved_at DATETIME")

    if statements:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))


def _ensure_sqlite_epic12_columns(engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    # projects.deck_hash
    if "projects" in tables:
        cols = {c["name"] for c in inspector.get_columns("projects")}
        if "deck_hash" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE projects ADD COLUMN deck_hash VARCHAR"))

    # project_slides.content_hash
    if "project_slides" in tables:
        cols = {c["name"] for c in inspector.get_columns("project_slides")}
        if "content_hash" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE project_slides ADD COLUMN content_hash VARCHAR NOT NULL DEFAULT ''"))


def get_db() -> Generator[Session, None, None]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine())
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
