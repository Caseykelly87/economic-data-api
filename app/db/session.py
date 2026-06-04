from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Construct the process-wide SQLAlchemy engine lazily on first call
    and memoize it. Importing this module no longer builds a
    connection-pooled engine as an import side effect; the engine is
    created on first real use, mirroring the lazy get_settings()
    convention in app.core.config."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker:
    """Memoized sessionmaker bound to the lazy engine. Binding at call
    time rather than at import keeps module import side-effect-free; a
    module-level sessionmaker(bind=get_engine()) would reintroduce the
    import-time engine construction this refactor removes."""
    return sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
