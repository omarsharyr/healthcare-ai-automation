import logging
import time

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def wait_for_database(engine: Engine, attempts: int, interval_seconds: float) -> None:
    """Bounded connection retries; never log database exceptions or connection URLs."""
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("database_available")
            return
        except SQLAlchemyError:
            logger.warning("database_wait_retry", extra={"attempt": attempt, "max_attempts": attempts})
            if attempt < attempts:
                time.sleep(interval_seconds)
    raise RuntimeError("Database unavailable after startup retries") from None
