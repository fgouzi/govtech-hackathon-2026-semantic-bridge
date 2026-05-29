from typing import Annotated

from fastapi import APIRouter, Depends

from adapters.mcp.client import MCPClient
from api.dependencies import get_mcp_client

router = APIRouter()


@router.get("/health")
async def health(client: Annotated[MCPClient, Depends(get_mcp_client)]) -> dict:
    return {
        "status": "ok",
        "version": "0.1.0",
        "mcp_connected": True,
        "mcp_url": client.active_url,
        "mcp_mode": "live" if client.is_live else "mock",
    }
