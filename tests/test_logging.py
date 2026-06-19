import json
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.context import request_id_var
from src.observability.logging import (
    CustomJSONFormatter,
    RequestIDFilter,
    setup_logging,
)


def test_setup_logging_runs_without_error() -> None:
    setup_logging()

    logger = logging.getLogger("tests.logging")
    logger.info("logging smoke test")


def test_json_formatter_preserves_extra_fields() -> None:
    formatter = CustomJSONFormatter(
        fmt_keys={
            "level": "levelname",
            "message": "message",
            "logger": "name",
        }
    )
    record = logging.LogRecord(
        name="tests.logging",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.tenant = "demo"

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["logger"] == "tests.logging"
    assert payload["request_id"] == "req-123"
    assert payload["tenant"] == "demo"


def test_request_id_filter_injects_context_request_id() -> None:
    token = request_id_var.set("req-context")
    try:
        record = logging.LogRecord(
            name="tests.logging",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )

        assert RequestIDFilter().filter(record) is True
        assert record.request_id == "req-context"
    finally:
        request_id_var.reset(token)


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
