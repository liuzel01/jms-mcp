import unittest
import os

os.environ.setdefault("jumpserver_url", "https://jumpserver.example")
os.environ.setdefault("access_key_id", "test-access-key")
os.environ.setdefault("access_key_secret", "test-access-key-secret")
os.environ.setdefault("api_key", "test-entry-key-that-is-at-least-thirty-two-characters")

import httpx

from jumpserver_mcp_server.client import JumpServerClient


class JumpServerClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_asset_list_is_a_bounded_get_request(self) -> None:
        observed: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            observed["method"] = request.method
            observed["path"] = request.url.path
            observed["params"] = dict(request.url.params)
            return httpx.Response(200, json={"count": 0, "results": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(base_url="https://jumpserver.example", transport=transport) as raw:
            client = JumpServerClient(raw, max_asset_page_size=100)
            result = await client.list_assets(search="prod", limit=20, offset=0)

        self.assertEqual(result, {"count": 0, "results": []})
        self.assertEqual(observed["method"], "GET")
        self.assertEqual(observed["path"], "/api/v1/assets/assets/")
        self.assertEqual(observed["params"], {"limit": "20", "offset": "0", "search": "prod"})

    async def test_asset_list_rejects_an_unbounded_limit_before_request(self) -> None:
        async with httpx.AsyncClient(base_url="https://jumpserver.example") as raw:
            client = JumpServerClient(raw, max_asset_page_size=100)
            with self.assertRaisesRegex(ValueError, "between 1 and 100"):
                await client.list_assets(search=None, limit=101, offset=0)

    async def test_asset_id_must_be_a_uuid(self) -> None:
        async with httpx.AsyncClient(base_url="https://jumpserver.example") as raw:
            client = JumpServerClient(raw, max_asset_page_size=100)
            with self.assertRaises(ValueError):
                await client.get_asset("not-a-uuid")
