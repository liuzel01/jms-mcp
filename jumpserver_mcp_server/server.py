"""This module implements the JumpServer MCP server.

It includes:
- A custom implementation of FastApiMCP for JumpServer.
- Middleware for API key validation.
- Utility classes and functions for OpenAPI schema handling.
"""

import base64
import datetime
import hashlib
import hmac
import typing
from logging import getLogger
from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi_mcp import FastApiMCP
from fastapi_mcp.openapi.convert import convert_openapi_to_mcp_tools
from fastapi_mcp.transport.sse import FastApiSseTransport
import mcp.types as types
from mcp.server.lowlevel.server import Server

from .config import settings
from .setup import setup_logging
from .tool_policy import ToolPolicyError, parse_operation_allowlist, select_read_only_tools

setup_logging(settings.log_level, debug=settings.debug)

logger = getLogger(__name__)


class JumpServerOpenapiMCP(FastApiMCP):
    """A custom implementation of FastApiMCP for JumpServer.

    This class extends FastApiMCP to integrate with JumpServer's API,
    providing functionality to convert OpenAPI schemas to MCP tools,
    filter tools, and handle tool calls.

    Attributes:
        api_token: The API token used for authentication.
        swagger_json: The OpenAPI schema in JSON format.
    """

    def __init__(self, app: FastAPI, **kwargs: Any) -> None:
        api_token = kwargs.pop("api_token")
        self.api_token = api_token
        self.swagger_json = kwargs.pop("swagger_json")
        self.base_url = kwargs.pop("base_url", None)
        self.sse_transport = None
        super().__init__(app, **kwargs)

    def is_auth_session(self, session_id: str) -> bool:
        if not self.sse_transport:
            return False
        if not session_id:
            return False
        try:
            session_id = UUID(session_id)
        except ValueError:
            return False
        sse_transport = self.sse_transport
        return session_id in sse_transport._read_stream_writers

    def setup_server(self) -> None:
        """Set up the MCP server by converting OpenAPI schema to tools.

        Filter tools and register handlers for tool listing and tool calls.
        """
        # Get OpenAPI schema from FastAPI app
        openapi_schema = self.swagger_json

        # Convert OpenAPI schema to MCP tools
        all_tools, operation_map = convert_openapi_to_mcp_tools(
            openapi_schema,
            describe_all_responses=self._describe_all_responses,
            describe_full_response_schema=self._describe_full_response_schema,
        )
        logger.info("Loaded %d tools from OpenAPI schema.", len(all_tools))

        enabled_operations = parse_operation_allowlist(settings.mcp_tool_allowlist)
        try:
            self.tools, self.operation_map = select_read_only_tools(
                all_tools, operation_map, enabled_operations
            )
        except ToolPolicyError:
            logger.exception("MCP tool policy validation failed during startup.")
            raise
        logger.info("Exposed %d explicitly allowlisted read-only MCP tools.", len(self.tools))

        # Normalize base URL
        self._base_url = self._base_url.removesuffix("/")

        # Create the MCP lowlevel server
        mcp_server: Server = Server(self.name, self.description)

        # Register handlers for tools
        @mcp_server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            return self.tools

        # Register the tool call handler
        @mcp_server.call_tool()
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            if name not in self.operation_map:
                raise ValueError(f"MCP tool is not enabled: {name}")
            try:
                ctx = mcp_server.request_context
                session = ctx.session
                experimental = session._init_options.capabilities.experimental
                authorization = experimental.get("session_token", {}).get("authorization")
                logger.debug("Session token authorization: %s", authorization)
            except Exception as e:
                logger.error("Error getting session token: %s", e)
                authorization = ""
            if upstream_auth is not None:
                http_client = httpx.AsyncClient(
                    auth=upstream_auth, base_url=self.base_url, verify=False, timeout=60
                )
            elif authorization:
                http_client = httpx.AsyncClient(
                    base_url=self.base_url,
                    verify=False,
                    headers={"Authorization": authorization},
                    timeout=60,
                )
            else:
                http_client = httpx.AsyncClient(base_url=self.base_url, verify=False, timeout=60)
            return await self._execute_api_tool(
                client=http_client,
                tool_name=name,
                arguments=arguments,
                operation_map=self.operation_map,
            )

        self.server = mcp_server

    def mount(self, router: Optional[FastAPI | APIRouter] = None, mount_path: str = "/mcp") -> None:
        """
        Mount the MCP server to **any** FastAPI app or APIRouter.
        There is no requirement that the FastAPI app or APIRouter is the same as the one that the MCP
        server was created from.

        Args:
            router: The FastAPI app or APIRouter to mount the MCP server to. If not provided, the MCP
                    server will be mounted to the FastAPI app.
            mount_path: Path where the MCP server will be mounted
        """
        # Normalize mount path
        if not mount_path.startswith("/"):
            mount_path = f"/{mount_path}"
        if mount_path.endswith("/"):
            mount_path = mount_path[:-1]

        if not router:
            router = self.fastapi

        # Build the base path correctly for the SSE transport
        if isinstance(router, FastAPI):
            base_path = router.root_path
        elif isinstance(router, APIRouter):
            base_path = self.fastapi.root_path + router.prefix
        else:
            raise ValueError(f"Invalid router type: {type(router)}")

        messages_path = f"{base_path}{mount_path}/messages/"

        sse_transport = FastApiSseTransport(messages_path)
        self.sse_transport = sse_transport

        # Route for MCP connection
        @router.get(mount_path, include_in_schema=False, operation_id="mcp_connection")
        async def handle_mcp_connection(request: Request):
            async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (
                reader,
                writer,
            ):
                authorization = request.headers.get("authorization", "")
                await self.server.run(
                    reader,
                    writer,
                    self.server.create_initialization_options(
                        notification_options=None,
                        experimental_capabilities={
                            "session_token": {"authorization": authorization},
                        },
                    ),
                )

        # Route for MCP messages
        @router.post(
            f"{mount_path}/messages/", include_in_schema=False, operation_id="mcp_messages"
        )
        async def handle_post_message(request: Request):
            return await sse_transport.handle_fastapi_post_message(request)

        # HACK: If we got a router and not a FastAPI instance, we need to re-include the router so that
        # FastAPI will pick up the new routes we added. The problem with this approach is that we assume
        # that the router is a sub-router of self.fastapi, which may not always be the case.
        #
        # TODO: Find a better way to do this.
        if isinstance(router, APIRouter):
            self.fastapi.include_router(router)

        logger.info(f"MCP server listening at {mount_path}")


class BearerAuth(httpx.Auth):
    """Allows the 'auth' argument to be passed as a token string or bytes.

    and uses HTTP Bearer authentication.
    """

    def __init__(self, token: str | bytes) -> None:
        """Initialize the BearerAuth instance with a token.

        Args:
            token (str | bytes): The token to be used for Bearer authentication.
        """
        self._auth_header = self._build_auth_header(token)

    def auth_flow(
        self, request: httpx.Request
    ) -> typing.Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = self._auth_header
        yield request

    def _build_auth_header(self, token: str | bytes) -> str:
        return f"Bearer {token}"


class JumpServerSignatureAuth(httpx.Auth):
    """HTTP Signature authentication for JumpServer API access keys."""

    requires_request_body = False

    def __init__(self, key_id: str, secret: str, organization: str) -> None:
        self.key_id = key_id
        self.secret = secret
        self.organization = organization

    def auth_flow(self, request: httpx.Request) -> typing.Generator[httpx.Request, httpx.Response, None]:
        date = datetime.datetime.now(datetime.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        path = request.url.raw_path.decode('ascii')
        accept = request.headers.get('accept', 'application/json')
        canonical = (
            f"(request-target): {request.method.lower()} {path}\n"
            f"accept: {accept}\n"
            f"date: {date}"
        )
        signature = base64.b64encode(
            hmac.new(self.secret.encode(), canonical.encode(), hashlib.sha256).digest()
        ).decode()
        request.headers['Accept'] = accept
        request.headers['Date'] = date
        request.headers['X-JMS-ORG'] = self.organization
        request.headers['Authorization'] = (
            f'Signature keyId="{self.key_id}",algorithm="hmac-sha256",'
            f'headers="(request-target) accept date",signature="{signature}"'
        )
        yield request


HTTP_OK = 200


class OpenAPISchemaFetchError(Exception):
    """Custom exception for OpenAPI schema fetch errors."""

    pass


def get_swagger_json(url: str = settings.swagger_url) -> dict[str, Any]:
    """Fetch the OpenAPI schema from the given URL.

    Args:
        url (str): The URL to fetch the OpenAPI schema from. Defaults to settings.swagger_url.

    Returns:
        dict[str, Any]: The OpenAPI schema in JSON format.

    Raises:
        OpenAPISchemaFetchError: If the schema cannot be fetched or the response status is not HTTP_OK.
    """
    kwargs = {"verify": False, "timeout": 120}

    if settings.access_key_id and settings.access_key_secret:
        kwargs["auth"] = JumpServerSignatureAuth(
            settings.access_key_id, settings.access_key_secret, settings.jms_org
        )
    elif settings.api_token:
        # If an API token is provided, use BearerAuth for authentication
        auth = BearerAuth(settings.api_token)
        kwargs["auth"] = auth
    resp = httpx.get(url, **kwargs)
    if resp.status_code != HTTP_OK:
        error_message = f"Failed to fetch OpenAPI schema: {resp.status_code} - {resp.text}"
        raise OpenAPISchemaFetchError(error_message)
    return resp.json()


app = FastAPI()
jumpserver_url = settings.jumpserver_url
base_url = settings.api_base_url
if not base_url and jumpserver_url:
    # JumpServer's Swagger paths are absolute (for example, /api/health/ and
    # /api/v1/assets/assets/), so the upstream client must use the origin.
    base_url = jumpserver_url
    logger.info("Base API URL set to: %s", base_url)
swagger_url = settings.swagger_url
if not swagger_url and jumpserver_url:
    # swagger_url = f"{jumpserver_url}/api/docs/?format=openapi"
    swagger_url = f"{jumpserver_url}/api/swagger.json"
    logger.info("Swagger URL set to: %s", swagger_url)
logger.info("Fetching OpenAPI schema from API URL: %s", swagger_url)
swagger_json = get_swagger_json(swagger_url)
upstream_auth: httpx.Auth | None = None
if settings.access_key_id and settings.access_key_secret:
    upstream_auth = JumpServerSignatureAuth(
        settings.access_key_id, settings.access_key_secret, settings.jms_org
    )
elif settings.api_token:
    upstream_auth = BearerAuth(settings.api_token)
http_client = httpx.AsyncClient(auth=upstream_auth, base_url=base_url, verify=False)
mcp = JumpServerOpenapiMCP(
    app,
    name="JumpServer API MCP",
    base_url=base_url,
    describe_all_responses=True,  # Include all possible response schemas in tool descriptions
    describe_full_response_schema=True,  # Include full JSON schema in tool descriptions
    api_token=settings.api_token,
    http_client=http_client,
    swagger_json=swagger_json,
)
http_mount_path = settings.http_base_path.strip('"').strip("'")
if not http_mount_path.startswith("/"):
    http_mount_path = "/" + http_mount_path
mcp.mount_http(mount_path=http_mount_path)
logger.info("Mounting streamable HTTP MCP at path: %s", f"{app.root_path}{http_mount_path}")

sse_mount_path = settings.base_path.strip('"').strip("'")
if not sse_mount_path.startswith("/"):
    sse_mount_path = "/" + sse_mount_path
mcp.mount(mount_path=sse_mount_path)
logger.info("Mounting legacy SSE MCP at path: %s", f"{app.root_path}{sse_mount_path}")


@app.middleware("http")
async def check_api_key(request: Request, call_next) -> Response:
    """Middleware to check the Bearer API key in the request headers.

    This middleware validates the Bearer API key provided in the request headers.
    """
    session_id_param = request.query_params.get("session_id")
    if session_id_param:
        if mcp.is_auth_session(session_id_param):
            return await call_next(request)
        else:
            logger.error("Unauthorized access attempt detected: session_id %s", session_id_param)
            return Response(status_code=401, content="Unauthorized: Invalid session ID")
    if settings.api_key:
        api_key = request.headers.get("Authorization")
        if (
            not api_key
            or not api_key.startswith("Bearer ")
            or api_key != f"Bearer {settings.api_key}"
        ):
            logger.error("Unauthorized access attempt detected")
            return Response(status_code=401, content="Unauthorized: Invalid API token")
    return await call_next(request)
