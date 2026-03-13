"""JSON serialization helpers for Konecty API (e.g. $date format)."""

from datetime import datetime
from typing import Any

from .exceptions import KonectySerializationError


def json_serial(obj: Any) -> Any:
    """Serialize objects to JSON-friendly form (e.g. datetime -> $date)."""
    if isinstance(obj, datetime):
        return {"$date": obj.isoformat()}
    raise KonectySerializationError()
