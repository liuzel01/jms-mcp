"""Explicit, read-only MCP tools for daily JumpServer operations."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .client import JumpServerClient
from .config import settings


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

mcp = FastMCP(
    name="JumpServer Operations",
    instructions=(
        "This server provides explicitly implemented, read-only JumpServer "
        "operations. It cannot create, update, delete, or launch sessions."
    ),
    streamable_http_path="/",
)


@mcp.tool(
    name="get_jumpserver_health",
    description="Return JumpServer API, database, and Redis health status.",
    annotations=READ_ONLY,
)
async def get_jumpserver_health() -> dict[str, Any]:
    async with JumpServerClient.from_settings(settings) as client:
        return await client.get_health()


@mcp.tool(
    name="list_jumpserver_assets",
    description="List assets visible to the configured JumpServer system user.",
    annotations=READ_ONLY,
)
async def list_jumpserver_assets(
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List a bounded page of assets, optionally filtered by a search string."""
    async with JumpServerClient.from_settings(settings) as client:
        return await client.list_assets(search=search, limit=limit, offset=offset)


@mcp.tool(
    name="get_jumpserver_asset",
    description="Return details for one asset visible to the configured system user.",
    annotations=READ_ONLY,
)
async def get_jumpserver_asset(asset_id: str) -> dict[str, Any]:
    async with JumpServerClient.from_settings(settings) as client:
        return await client.get_asset(asset_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start FastMCP's session manager when mounted under FastAPI."""
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="JumpServer Operations MCP", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def require_entry_api_key(request: Request, call_next) -> Response:
    """Require the configured bearer key for every MCP request."""
    if request.url.path.startswith("/mcp") and not settings.is_valid_entry_api_key(
        request.headers.get("authorization")
    ):
        return Response(status_code=401, content="Unauthorized")
    return await call_next(request)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Liveness endpoint; it deliberately does not call JumpServer."""
    return {"status": "ok"}


app.mount("/mcp", mcp.streamable_http_app())
