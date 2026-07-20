"""Logging setup with secret redaction (docs/11_SECURITY.md).

Never logs BROKER_API_TOKEN / OANDA_API_TOKEN / APP_API_TOKEN values, even if a
caller accidentally passes them into a log message.
"""
from __future__ import annotations

import logging
import re

from app.core.config import get_settings

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-_.]+", re.IGNORECASE),
    re.compile(r"(api[_-]?token[\"'=:\s]+)[A-Za-z0-9\-_.]{8,}", re.IGNORECASE),
    re.compile(r"(api[_-]?secret[\"'=:\s]+)[A-Za-z0-9\-_.]{8,}", re.IGNORECASE),
    re.compile(r"(api[_-]?key[\"'=:\s]+)[A-Za-z0-9\-_.]{8,}", re.IGNORECASE),
]


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = msg
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(r"\1***REDACTED***", redacted)
        settings = get_settings()
        for secret in (
            settings.app_api_token,
            settings.oanda_api_token,
            settings.gmo_coin_api_key,
            settings.gmo_coin_api_secret,
            settings.ai_api_key,
        ):
            if secret and len(secret) >= 6:
                redacted = redacted.replace(secret, "***REDACTED***")
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(RedactSecretsFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)
