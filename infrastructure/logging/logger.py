"""Structured logging with secret scrubbing for the Swing Trading AI Platform."""

from __future__ import annotations

import logging
import re
import sys
from typing import Iterable


SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|secret|token|password|authorization)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{6,})['\"]?", re.I),
]


class SecretScrubbingFilter(logging.Filter):
    """Ensures no API keys or credentials are emitted into application logs."""

    def __init__(self, explicit_secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = [s for s in explicit_secrets if s and len(s) >= 4]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        scrubbed = msg
        for secret in self._secrets:
            if secret in scrubbed:
                scrubbed = scrubbed.replace(secret, "***REDACTED***")
        for pat in SECRET_PATTERNS:
            scrubbed = pat.sub(r"\1=***REDACTED***", scrubbed)
        if scrubbed != msg:
            record.msg = scrubbed
            record.args = ()
        return True


def get_logger(name: str, explicit_secrets: Iterable[str] = ()) -> logging.Logger:
    """Create or retrieve a structured logger with secret scrubbing enabled."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SecretScrubbingFilter(explicit_secrets))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger

