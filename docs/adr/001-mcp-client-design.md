# ADR 001 — Custom MCP Client over Official Python SDK

**Status:** Accepted  
**Date:** 2026-05-28

## Context

The official Anthropic MCP Python SDK (`mcp` on PyPI) provides a `ClientSession` abstraction
that handles transport, message routing, and lifecycle. However, for this project we need:

1. **Transparent fallback** — seamlessly switch from I14Y to a local mock server without
   restarting the client or raising errors to callers.
2. **SQLite-backed caching** — cache `tools/list` and `search_concepts` responses with TTL
   to survive offline demos.
3. **Custom retry logic** — exponential backoff on connection errors, not just timeouts.
4. **Windows-compatible async SSE** — the official SDK has some edge cases on Windows with
   `anyio` + `asyncio` event loop interactions.
5. **Minimal dependencies** — the official SDK pulls in `anyio`, `starlette`, and other
   server-side dependencies that aren't needed for a pure client.

## Decision

Build a lightweight custom MCP client using:

- **`httpx`** — async HTTP client for POST requests (JSON-RPC messages)
- **`httpx-sse`** — async SSE streaming via `aconnect_sse()` / `aiter_sse()`
- **`pydantic v2`** — message validation and serialization
- **`aiosqlite`** — async SQLite for response caching

The client exposes three public methods:
```python
await client.connect() -> bool          # True=live, False=mock
await client.list_tools() -> list[MCPTool]
await client.call_tool(name, args) -> MCPToolResult
```

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Official `mcp` SDK | Standards-compliant, maintained | Heavy deps, no fallback, Windows issues |
| `fastmcp` client | Simpler API | Alpha quality, undocumented client mode |
| Custom (chosen) | Full control, minimal deps | Must maintain JSON-RPC compliance |

## Consequences

✅ Full control over fallback and caching  
✅ Minimal dependency surface (httpx already a project dep)  
✅ Easy to unit test with `httpx.MockTransport`  
❌ Must maintain JSON-RPC 2.0 compliance manually  
❌ SSE reconnection logic (cursor/Last-Event-ID) must be implemented explicitly if needed  
