from typing import Any

from pydantic import BaseModel, Field


class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Any = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any = None
    error: JSONRPCError | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


class MCPToolInputSchema(BaseModel):
    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class MCPTool(BaseModel):
    name: str
    description: str
    inputSchema: MCPToolInputSchema = Field(default_factory=MCPToolInputSchema)


class MCPToolResult(BaseModel):
    content: list[dict[str, Any]] = Field(default_factory=list)
    isError: bool = False

    def text(self) -> str:
        for item in self.content:
            if item.get("type") == "text":
                return str(item.get("text", ""))
        return ""


class MCPServerCapabilities(BaseModel):
    tools: dict[str, Any] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(default_factory=dict)
    prompts: dict[str, Any] = Field(default_factory=dict)


class MCPInitializeResult(BaseModel):
    protocolVersion: str
    capabilities: MCPServerCapabilities = Field(default_factory=MCPServerCapabilities)
    serverInfo: dict[str, Any] = Field(default_factory=dict)
