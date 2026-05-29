import json
from typing import Any

from adapters.mcp.models import JSONRPCResponse, MCPInitializeResult, MCPTool, MCPToolResult

_PROTOCOL_VERSION = "2024-11-05"
_CLIENT_NAME = "semantic-bridge"
_CLIENT_VERSION = "0.1.0"


def build_initialize(request_id: int = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "clientInfo": {"name": _CLIENT_NAME, "version": _CLIENT_VERSION},
        },
    }


def build_tools_list(request_id: int = 2) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}}


def build_tool_call(name: str, arguments: dict[str, Any], request_id: int = 3) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def build_initialized_notification() -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}


def parse_response(raw: dict[str, Any] | str) -> JSONRPCResponse:
    if isinstance(raw, str):
        raw = json.loads(raw)
    return JSONRPCResponse.model_validate(raw)


def parse_initialize_result(response: JSONRPCResponse) -> MCPInitializeResult:
    if response.is_error:
        raise ValueError(f"Initialize failed: {response.error}")
    return MCPInitializeResult.model_validate(response.result)


def parse_tools_list(response: JSONRPCResponse) -> list[MCPTool]:
    if response.is_error:
        raise ValueError(f"tools/list failed: {response.error}")
    tools_raw = response.result.get("tools", []) if response.result else []
    return [MCPTool.model_validate(t) for t in tools_raw]


def parse_tool_result(response: JSONRPCResponse) -> MCPToolResult:
    if response.is_error:
        return MCPToolResult(
            content=[{"type": "text", "text": str(response.error)}], isError=True
        )
    return MCPToolResult.model_validate(response.result or {})
