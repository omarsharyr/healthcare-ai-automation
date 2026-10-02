"""Backend entry point used by Docker and optional host development."""
import logging

import uvicorn

from app.core.config import get_settings
from app.core.logging import configure_logging, logging_config
from app.db.config import get_database_settings
from app.db.session import get_engine
from app.db.startup import wait_for_database

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    try:
        settings = get_settings()
        configure_logging(settings.log_level)
        database = get_database_settings()
        wait_for_database(get_engine(), database.db_startup_attempts, database.db_retry_interval_seconds)
    except Exception:
        logger.error("backend_startup_failed")
        return 1
    logger.info("backend_starting")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port,
                log_config=logging_config(settings.log_level), access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
