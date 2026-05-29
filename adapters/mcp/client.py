import itertools
from typing import Any

from adapters.mcp import models, protocol
from adapters.mcp.transport import MCPTransport
from adapters.cache import SQLiteCache
from core.exceptions import MCPConnectionError
from core.logging import get_logger

log = get_logger(__name__)
_id_counter = itertools.count(1)

_SESSION_HEADER = "mcp-session-id"


class MCPClient:
    """Async MCP client — supports MCP Streamable HTTP (2024-11-05) with session IDs.

    Connects to primary URL (I14Y live server). On failure, falls back transparently
    to a local mock MCP server. Session IDs are captured from initialize response
    headers and forwarded on all subsequent requests.
    """

    def __init__(self, primary_url: str, fallback_url: str, cache: SQLiteCache) -> None:
        self._primary_url = primary_url
        self._fallback_url = fallback_url
        self._active_url: str = primary_url
        self._cache = cache
        self._transport = MCPTransport()
        self._using_mock = False
        # Session IDs per server URL (Streamable HTTP protocol)
        self._session_ids: dict[str, str] = {}

    async def __aenter__(self) -> "MCPClient":
        await self._transport.__aenter__()
        await self._cache.initialize()
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._transport.__aexit__(*args)

    async def connect(self) -> bool:
        """Connect to primary MCP server; fall back to mock on failure.

        Returns True if connected to the live I14Y server, False if using mock.
        """
        try:
            await self._handshake(self._primary_url)
            self._active_url = self._primary_url
            self._using_mock = False
            sid = self._session_ids.get(self._primary_url, "none")
            log.info("mcp_connected", url=self._primary_url, session_id=sid[:8] + "…")
            return True
        except (MCPConnectionError, Exception) as exc:
            log.warning("mcp_primary_failed", url=self._primary_url, reason=str(exc))
            try:
                await self._handshake(self._fallback_url)
                self._active_url = self._fallback_url
                self._using_mock = True
                log.info("mcp_using_mock", url=self._fallback_url)
                return False
            except Exception as exc2:
                log.error("mcp_fallback_failed", url=self._fallback_url, reason=str(exc2))
                self._active_url = self._fallback_url
                self._using_mock = True
                return False

    async def list_tools(self) -> list[models.MCPTool]:
        cache_key = f"tools_list:{self._active_url}"
        cached = await self._cache.get(cache_key)
        if cached and isinstance(cached, list):
            return [models.MCPTool.model_validate(t) for t in cached]

        req = protocol.build_tools_list(next(_id_counter))
        raw = await self._transport.post_message(
            self._active_url, req, session_id=self._session_id
        )
        response = protocol.parse_response(raw)
        tools = protocol.parse_tools_list(response)

        await self._cache.set(cache_key, [t.model_dump() for t in tools])
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> models.MCPToolResult:
        cache_key = f"tool_call:{self._active_url}:{name}:{sorted(arguments.items())}"
        cached = await self._cache.get(cache_key)
        if cached:
            return models.MCPToolResult.model_validate(cached)

        req = protocol.build_tool_call(name, arguments, next(_id_counter))
        raw = await self._transport.post_message(
            self._active_url, req, session_id=self._session_id
        )
        response = protocol.parse_response(raw)
        result = protocol.parse_tool_result(response)

        if not result.isError:
            await self._cache.set(cache_key, result.model_dump(), ttl_seconds=3600)

        return result

    async def _handshake(self, url: str) -> None:
        req = protocol.build_initialize(next(_id_counter))
        body, resp_headers = await self._transport.post_initialize(url, req)

        # Capture session ID (MCP Streamable HTTP protocol)
        session_id = resp_headers.get(_SESSION_HEADER) or resp_headers.get(_SESSION_HEADER.lower())
        if session_id:
            self._session_ids[url] = session_id
            log.debug("mcp_session_captured", url=url, session_id=session_id[:8] + "…")

        response = protocol.parse_response(body)
        protocol.parse_initialize_result(response)

        # Send initialized notification (best-effort, carries session ID)
        notif = protocol.build_initialized_notification()
        try:
            await self._transport.post_message(url, notif, session_id=session_id)
        except Exception:
            pass

    @property
    def _session_id(self) -> str | None:
        return self._session_ids.get(self._active_url)

    @property
    def is_live(self) -> bool:
        return not self._using_mock

    @property
    def active_url(self) -> str:
        return self._active_url
