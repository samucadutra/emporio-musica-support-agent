"""PII-safe JSON logging (design §12)."""

import json
import logging

from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.logging_setup import (
    LOGGER_NAME,
    PIIMaskingFilter,
    configure,
    log_event,
)


def read_log(settings: Settings) -> list[dict[str, object]]:
    for handler in logging.getLogger(LOGGER_NAME).handlers:
        handler.flush()
    lines = settings.log_file.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_email_and_phone_masked_in_message_and_fields(tmp_settings: Settings) -> None:
    configure(tmp_settings)
    logger = logging.getLogger(f"{LOGGER_NAME}.test")

    logger.warning("cliente leticia.rocha@jmail.com ligou de (67) 99789-0123")
    log_event(
        logger,
        "tool_call",
        args={"email": "leticia.rocha@jmail.com", "order_id": 7},
        summary="contato 67997890123",
    )
    records = read_log(tmp_settings)
    text = json.dumps(records, ensure_ascii=False)

    assert "leticia.rocha@jmail.com" not in text
    assert "99789-0123" not in text
    assert "67997890123" not in text
    assert "le***@jmail.com" in str(records[0]["message"])
    assert records[1]["event"] == "tool_call"
    assert records[1]["args"] == {"email": "le***@jmail.com", "order_id": 7}


def test_every_handler_masks_and_reconfigure_does_not_stack(tmp_settings: Settings) -> None:
    configure(tmp_settings)
    configure(tmp_settings, verbose=True)
    handlers = logging.getLogger(LOGGER_NAME).handlers

    assert len(handlers) == 2
    assert all(any(isinstance(f, PIIMaskingFilter) for f in h.filters) for h in handlers)
    assert logging.getLogger(LOGGER_NAME).propagate is False
