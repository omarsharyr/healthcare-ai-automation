"""One-shot migration command with retries and a PostgreSQL transaction lock."""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, pool, text

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.config import get_database_settings
from app.db.startup import wait_for_database

logger = logging.getLogger(__name__)
# Stable, application-specific lock; all instances of this runner share it.
MIGRATION_LOCK_ID = 728461903


def upgrade_database(engine: Engine, lock_timeout_seconds: int = 30) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    with engine.begin() as connection:
        connection.execute(text("SELECT set_config('lock_timeout', :timeout, true)"),
                           {"timeout": f"{lock_timeout_seconds}s"})
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_ID})
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def main() -> int:
    configure_logging()
    engine: Engine | None = None
    try:
        configure_logging(get_settings().log_level)
        settings = get_database_settings()
        engine = create_engine(
            settings.sqlalchemy_url(), poolclass=pool.NullPool,
            hide_parameters=True, echo=False,
            connect_args={"connect_timeout": settings.db_connect_timeout},
        )
        wait_for_database(engine, settings.db_startup_attempts, settings.db_retry_interval_seconds)
        upgrade_database(engine, settings.db_migration_lock_timeout_seconds)
        logger.info("migrations_completed")
        return 0
    except Exception:
        # Exceptions from migrations/settings may contain SQL, row data, or credentials.
        logger.error("migrations_failed")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
