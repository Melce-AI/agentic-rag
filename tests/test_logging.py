import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.observability.logging import setup_logging


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.debug("Test debug log")
    logger.info("Test info log")
    logger.warning("Test warning log")
    logger.info(
        "Test info log with extra",
        extra={"request_id": "req-123", "tenant": "demo"},
    )

    try:
        1 / 0
    except ZeroDivisionError:
        logger.exception("Test exception log")

    try:
        sample = {"ok": True}
        _ = sample["missing_key"]
    except KeyError:
        logger.error("Test error log with explicit exc_info", exc_info=True)

    try:
        int("not-a-number")
    except ValueError:
        logger.critical("Test critical log with exc_info", exc_info=True)

    logger.error("Test plain error log without traceback")
    logger.critical("Test plain critical log")


if __name__ == "__main__":
    main()
