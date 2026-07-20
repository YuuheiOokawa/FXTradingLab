"""Logging setup with secret redaction (docs/11_SECURITY.md) and optional
structured JSON output with request/order correlation IDs
(docs/15_PRODUCTION_READINESS_REVIEW.md "Observability").

Never logs BROKER_API_TOKEN / OANDA_API_TOKEN / APP_API_TOKEN values, even if a
caller accidentally passes them into a log message.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.request_context import get_order_id, get_request_id

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


class RequestContextFilter(logging.Filter):
    """Attaches request_id/order_id (if set for the current async context) to
    every log record so they can be correlated across modules — "why did this
    order fail" shouldn't require grepping timestamps."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.order_id = get_order_id()
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": get_settings().service_name,
            "event": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "order_id": getattr(record, "order_id", None),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler()
    if settings.log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [req=%(request_id)s]: %(message)s")
        )
    handler.addFilter(RedactSecretsFilter())
    handler.addFilter(RequestContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)
