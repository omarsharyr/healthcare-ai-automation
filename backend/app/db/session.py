from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.config import get_database_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_database_settings()
    return create_engine(
        settings.sqlalchemy_url(),
        pool_pre_ping=True,
        pool_timeout=settings.db_pool_timeout,
        echo=False,
        hide_parameters=True,
        connect_args={
            "connect_timeout": settings.db_connect_timeout,
            "options": f"-cstatement_timeout={settings.db_statement_timeout_ms}",
        },
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session
