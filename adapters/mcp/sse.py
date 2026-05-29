import json
from typing import Any

from core.logging import get_logger

log = get_logger(__name__)


def parse_sse_data(data: str) -> dict[str, Any] | None:
    """Parse a single SSE data line into a JSON-RPC dict."""
    data = data.strip()
    if not data or data == ":":
        return None
    try:
        return json.loads(data)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        log.warning("sse_parse_error", data=data[:100])
        return None


def is_keepalive(event_data: str) -> bool:
    """Check if an SSE event is just a keepalive ping."""
    return event_data.strip() in ("", ":", "ping")
