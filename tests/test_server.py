import unittest
import os

os.environ.setdefault("jumpserver_url", "https://jumpserver.example")
os.environ.setdefault("access_key_id", "test-access-key")
os.environ.setdefault("access_key_secret", "test-access-key-secret")
os.environ.setdefault("api_key", "test-entry-key-that-is-at-least-thirty-two-characters")

from jumpserver_mcp_server.server import mcp
from fastapi.testclient import TestClient
from jumpserver_mcp_server.server import app


class ServerToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_explicit_read_only_tools_are_registered(self) -> None:
        tools = await mcp.list_tools()
        self.assertEqual(
            [tool.name for tool in tools],
            ["get_jumpserver_health", "list_jumpserver_assets", "get_jumpserver_asset"],
        )
        for tool in tools:
            self.assertTrue(tool.annotations.readOnlyHint)
            self.assertFalse(tool.annotations.destructiveHint)


class ServerHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_healthz_does_not_require_an_mcp_key(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_mcp_endpoint_requires_an_entry_key(self) -> None:
        response = self.client.post("/mcp")
        self.assertEqual(response.status_code, 401)
