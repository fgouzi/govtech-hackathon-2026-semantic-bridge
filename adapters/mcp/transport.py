import asyncio
import json
from typing import Any, AsyncIterator

import httpx
from httpx_sse import aconnect_sse

from adapters.mcp.sse import is_keepalive, parse_sse_data
from core.exceptions import MCPConnectionError, MCPProtocolError
from core.logging import get_logger

log = get_logger(__name__)

_TIMEOUT = httpx.Timeout(connect=8.0, read=30.0, write=10.0, pool=5.0)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5

_BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


class MCPTransport:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "MCPTransport":
        self._client = httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client:
            await self._client.aclose()

    async def post_initialize(
        self, url: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Send initialize and return (body, response_headers).

        Used to capture the mcp-session-id that the server sets in response headers.
        """
        client = self._get_client()
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.post(
                    url, content=json.dumps(payload), headers=_BASE_HEADERS
                )
                resp.raise_for_status()
                body = await self._parse_response_body(resp, url, payload)
                return body, dict(resp.headers)
            except httpx.ConnectError as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise MCPConnectionError(f"Cannot connect to {url}: {exc}") from exc
                await asyncio.sleep(_RETRY_BASE_DELAY * (2**attempt))
            except httpx.HTTPStatusError as exc:
                raise MCPProtocolError(f"HTTP {exc.response.status_code} from {url}") from exc
        raise MCPConnectionError(f"Exhausted retries for {url}")

    async def post_message(
        self,
        url: str,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and return the parsed JSON body."""
        client = self._get_client()
        headers = dict(_BASE_HEADERS)
        if session_id:
            headers["mcp-session-id"] = session_id

        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.post(url, content=json.dumps(payload), headers=headers)
                resp.raise_for_status()
                return await self._parse_response_body(resp, url, payload, session_id)
            except httpx.ConnectError as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise MCPConnectionError(f"Cannot connect to {url}: {exc}") from exc
                await asyncio.sleep(_RETRY_BASE_DELAY * (2**attempt))
            except httpx.HTTPStatusError as exc:
                raise MCPProtocolError(f"HTTP {exc.response.status_code} from {url}") from exc
        raise MCPConnectionError(f"Exhausted retries for {url}")

    async def _parse_response_body(
        self,
        resp: httpx.Response,
        url: str,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return await self._read_first_sse_from_response(resp)
        return resp.json()  # type: ignore[no-any-return]

    async def _read_first_sse_from_response(self, resp: httpx.Response) -> dict[str, Any]:
        """Parse the first data event from an already-received SSE body."""
        for line in resp.text.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                parsed = parse_sse_data(line[5:].strip())
                if parsed is not None:
                    return parsed
        raise MCPProtocolError("SSE response contained no parseable data event")

    async def stream_sse(
        self,
        url: str,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream all SSE events as JSON dicts (for long-running tool calls)."""
        client = self._get_client()
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if session_id:
            headers["mcp-session-id"] = session_id

        async with aconnect_sse(
            client, "POST", url, content=json.dumps(payload), headers=headers
        ) as event_source:
            async for event in event_source.aiter_sse():
                if is_keepalive(event.data):
                    continue
                parsed = parse_sse_data(event.data)
                if parsed is not None:
                    yield parsed

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("MCPTransport used outside async context manager")
        return self._client
