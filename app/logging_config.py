import json
import logging
import sys
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    """Small dependency-free JSON formatter for application logs."""

    fields = (
        "event",
        "request_id",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "user_id",
        "booking_id",
        "payment_id",
        "event_id",
        "result",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self.fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("healthcare")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
    return logger

