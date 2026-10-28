"""PII-safe logging: JSON lines to a file, Rich on the console (design §12).

Only the package logger is configured, so library noise stays out of the log.
Event fields travel under one `extra["fields"]` dict, because names such as
`args` are reserved `LogRecord` attributes.
"""

import json
import logging
from datetime import UTC, datetime

from rich.logging import RichHandler

from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.privacy import mask_pii

LOGGER_NAME = "emporio_musica_support_agent"


def _mask(value: object) -> object:
    if isinstance(value, str):
        return mask_pii(value)
    if isinstance(value, dict):
        return {key: _mask(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_mask(item) for item in value]
    return value


class PIIMaskingFilter(logging.Filter):
    """Masks emails and phones in the message and in event fields (NFR-02)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_pii(record.getMessage())
        record.args = None
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            record.fields = _mask(fields)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", None),
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure(settings: Settings, verbose: bool = False) -> None:
    """(Re)configure the package logger; calling it again replaces the handlers."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
    file_handler.setLevel(settings.log_level.upper())
    file_handler.setFormatter(JsonFormatter())

    console_handler = RichHandler(show_path=False, markup=False)
    console_handler.setLevel(logging.INFO if verbose else logging.WARNING)

    for handler in (file_handler, console_handler):
        handler.addFilter(PIIMaskingFilter())
        logger.addHandler(handler)


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    logger.info(event, extra={"event": event, "fields": fields})
