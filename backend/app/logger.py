"""
Centralized logging setup: Loguru → JSON stdout + Seq (CLEF) sink.

Usage:
    from app.logger import get_logger
    log = get_logger("sync")
    log.debug("query: {}", query)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import traceback

import httpx
from loguru import logger

SEQ_URL = os.getenv("SEQ_URL", "http://seq:5341")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


class _InterceptHandler(logging.Handler):
    """Route stdlib logging (uvicorn, sqlalchemy, litellm, …) through Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # type: ignore[assignment]
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _seq_sink(message: object) -> None:
    record = message.record  # type: ignore[attr-defined]
    event: dict = {
        "@t": record["time"].isoformat(),
        "@l": record["level"].name,
        "@mt": record["message"],
        "category": record["extra"].get("category", "app"),
        "file": record["file"].name,
        "line": record["line"],
        "function": record["function"],
    }
    for key in ("source", "app_id"):
        if key in record["extra"]:
            event[key] = record["extra"][key]
    if record["exception"]:
        event["@x"] = "".join(traceback.format_exception(*record["exception"]))
    try:
        httpx.post(
            f"{SEQ_URL}/api/events/raw",
            params={"clef": ""},
            content=json.dumps(event),
            headers={"Content-Type": "application/vnd.serilog.clef"},
            timeout=2.0,
        )
    except Exception:
        pass  # never let Seq unavailability affect the app


def setup_logging() -> None:
    logger.remove()

    # JSON on stdout — visible in `docker logs` and OrbStack
    logger.add(
        sys.stdout,
        level=LOG_LEVEL,
        serialize=True,
        enqueue=True,
    )

    # Seq: always DEBUG so you can filter in the UI
    logger.add(
        _seq_sink,
        level="DEBUG",
        enqueue=True,  # separate thread — never blocks requests
    )

    # Intercept all stdlib logging
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    # Silence noisy third-party loggers
    for name in ("uvicorn.access", "LiteLLM", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(category: str, source: str | None = None):
    """Return a Loguru logger bound to a category (and optional source) for Seq filtering."""
    extra: dict = {"category": category}
    if source:
        extra["source"] = source
    return logger.bind(**extra)
