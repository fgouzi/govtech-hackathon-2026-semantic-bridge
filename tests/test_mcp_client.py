"""Tests for MCP protocol and client layer."""

import json

import pytest

from adapters.mcp import protocol
from adapters.mcp.models import JSONRPCResponse, MCPTool
from adapters.mcp.sse import is_keepalive, parse_sse_data


class TestProtocolBuilders:
    def test_build_initialize(self) -> None:
        msg = protocol.build_initialize(1)
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "initialize"
        assert msg["id"] == 1
        assert "protocolVersion" in msg["params"]
        assert msg["params"]["clientInfo"]["name"] == "semantic-bridge"

    def test_build_tools_list(self) -> None:
        msg = protocol.build_tools_list(2)
        assert msg["method"] == "tools/list"
        assert msg["id"] == 2

    def test_build_tool_call(self) -> None:
        msg = protocol.build_tool_call("search_concepts", {"query": "birth date"}, 3)
        assert msg["method"] == "tools/call"
        assert msg["params"]["name"] == "search_concepts"
        assert msg["params"]["arguments"]["query"] == "birth date"


class TestProtocolParsers:
    def test_parse_response_success(self) -> None:
        raw = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        resp = protocol.parse_response(raw)
        assert not resp.is_error
        assert resp.result == {"tools": []}

    def test_parse_response_error(self) -> None:
        raw = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "Method not found"}}
        resp = protocol.parse_response(raw)
        assert resp.is_error
        assert resp.error.code == -32601  # type: ignore[union-attr]

    def test_parse_response_from_string(self) -> None:
        raw_str = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"ok": True}})
        resp = protocol.parse_response(raw_str)
        assert not resp.is_error

    def test_parse_tools_list(self) -> None:
        resp = JSONRPCResponse(
            id=2,
            result={
                "tools": [
                    {
                        "name": "search_concepts",
                        "description": "Search concepts",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            },
        )
        tools = protocol.parse_tools_list(resp)
        assert len(tools) == 1
        assert tools[0].name == "search_concepts"

    def test_parse_tool_result(self) -> None:
        resp = JSONRPCResponse(
            id=3,
            result={"content": [{"type": "text", "text": "hello"}], "isError": False},
        )
        result = protocol.parse_tool_result(resp)
        assert not result.isError
        assert result.text() == "hello"

    def test_parse_tool_result_error(self) -> None:
        resp = JSONRPCResponse(
            id=3,
            error={"code": -32000, "message": "Tool failed"},
        )
        result = protocol.parse_tool_result(resp)
        assert result.isError


class TestSSEParser:
    def test_parse_valid_json(self) -> None:
        data = '{"jsonrpc": "2.0", "id": 1, "result": {}}'
        parsed = parse_sse_data(data)
        assert parsed is not None
        assert parsed["jsonrpc"] == "2.0"

    def test_parse_empty_returns_none(self) -> None:
        assert parse_sse_data("") is None
        assert parse_sse_data("  ") is None

    def test_parse_invalid_json_returns_none(self) -> None:
        assert parse_sse_data("not json") is None

    def test_keepalive_detection(self) -> None:
        assert is_keepalive("") is True
        assert is_keepalive(":") is True
        assert is_keepalive("ping") is True
        assert is_keepalive('{"jsonrpc": "2.0"}') is False
