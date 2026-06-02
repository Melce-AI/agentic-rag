import atexit
import copy
import datetime as dt
import json
import logging
import logging.config
import logging.handlers
import pathlib
from typing import override

from src.core.config import get_settings


class QueueHandlerInit:
    """Ensures that the QueueListener for the QueueHandler is started exactly once, even in reload/multi-import scenarios."""
    _started = False

    def __init__(self, handler_name: str = "queue_handler") -> None:
        if QueueHandlerInit._started:
            return

        queue_handler = logging.getHandlerByName(handler_name)
        if queue_handler is None:
            return

        listener = getattr(queue_handler, "listener", None)
        if listener is None:
            return

        try:
            listener.start()
            atexit.register(listener.stop)
            QueueHandlerInit._started = True
        except RuntimeError:
            # Listener may already be running in reload/multi-import scenarios.
            QueueHandlerInit._started = True


class CustomQueueHandler(logging.handlers.QueueHandler):
    """QueueHandler variant that preserves exc_info for downstream formatters."""

    @override
    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        prepared = copy.copy(record)
        prepared.message = record.getMessage()
        prepared.msg = prepared.message
        prepared.args = None
        # Let downstream formatters decide how to render exception text.
        prepared.exc_text = None
        return prepared


class CustomJSONFormatter(logging.Formatter):
    """Custom JSON formatter that converts log records into structured JSON format."""
    def __init__(
            self,
            *,
            fmt_keys: dict[str, str] | None = None,
            builtin_attrs: list[str] | None = None,
    ):
        super().__init__()
        self.fmt_keys = fmt_keys if fmt_keys is not None else {}
        self.builtin_attrs = set(builtin_attrs) if builtin_attrs is not None else set()

    @override
    def format(self, record: logging.LogRecord) -> str:
        message = self._prepare_log_dict(record)
        return json.dumps(message, default=str)
    
    def _prepare_log_dict(self, record: logging.LogRecord) -> dict:
        always_fields = {
            "message": record.getMessage(),
            "timestamp": dt.datetime.fromtimestamp(record.created, tz=dt.timezone.utc).isoformat(),
        }
        if record.exc_info is not None:
            always_fields["exc_info"] = self.formatException(record.exc_info)

        if record.stack_info is not None:
            always_fields["stack_info"] = self.formatStack(record.stack_info)

        message = {
            key: msg_val
            if (msg_val := always_fields.pop(val, None)) is not None
            else getattr(record, val)
            for key, val in self.fmt_keys.items()
        }
        message.update(always_fields)

        for key, val in record.__dict__.items():
            if key not in self.builtin_attrs:
                message[key] = val

        return message


class NonErrorFilter(logging.Filter):
    """Logging filter that allows only log records with level INFO or below (DEBUG, INFO) to pass through."""
    @override
    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        # Only allow log records with level INFO or below (DEBUG, INFO) to pass through this filter
        return record.levelno <= logging.INFO


def _resolve_log_level(level_name: str) -> str:
    """Resolve user-provided level names safely; fallback to INFO when invalid."""
    normalized = (level_name or "INFO").strip().upper()
    return normalized if normalized in logging._nameToLevel else "INFO"


def setup_logging() -> None:
    """Initialize logging with dynamic terminal levels and persistent file logging.
    
    Features:
    - Terminal handler levels controlled by Settings.LOG_LEVEL (dynamic).
    - File log handler follows LOG_LEVEL dynamically. Useful for checking what your LOG_LEVEL actually captures.
    - File JSON handler always logs at DEBUG for full traceability (persistent).
    - Hierarchical loggers: src.api, src.core, src.adapters, src.rag etc. can be configured independently.
    - Non-blocking I/O via QueueHandler + QueueListener.
    - stdout/stderr separation: INFO and below go to stdout, WARNING+ to stderr.
    
    Logger hierarchy example:
        logger = logging.getLogger(__name__)  # Gets "src.api", "src.adapters", etc.
        
    Configure per-module levels in logging_config.json if needed.
    """

    config_file = pathlib.Path("src/observability/logging_config.json")
    with open(config_file, "r", encoding="utf-8") as f_in:
        config = json.load(f_in)

    settings = get_settings()
    terminal_level = _resolve_log_level(settings.LOG_LEVEL)

    stdout_handler = config.get("handlers", {}).get("stdout", {})
    stderr_handler = config.get("handlers", {}).get("stderr", {})
    file_log_handler = config.get("handlers", {}).get("file_log", {})

    # stdout remains dedicated to DEBUG/INFO due to NonErrorFilter; level decides if DEBUG and/or INFO are emitted.
    stdout_handler["level"] = terminal_level

    # stderr always handles WARNING+; if terminal level is stricter, it is applied dynamically.
    stderr_handler["level"] = (
        terminal_level
        if logging._nameToLevel[terminal_level] >= logging.WARNING
        else "WARNING"
    )

    # file_log follows terminal level directly (no filtering, no level restrictions).
    file_log_handler["level"] = terminal_level

    # Ensure file handler directories exist before dictConfig builds handlers.
    for handler in config.get("handlers", {}).values():
        filename = handler.get("filename") if isinstance(handler, dict) else None
        if filename:
            pathlib.Path(filename).parent.mkdir(parents=True, exist_ok=True)

    logging.config.dictConfig(config)
    QueueHandlerInit()
