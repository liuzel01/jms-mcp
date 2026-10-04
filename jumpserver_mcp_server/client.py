"""Small, explicit read-only client for the JumpServer REST API."""

from typing import Any
from uuid import UUID

import httpx

from .auth import JumpServerSignatureAuth
from .config import Settings


class JumpServerClient:
    def __init__(self, client: httpx.AsyncClient, max_asset_page_size: int) -> None:
        self._client = client
        self._max_asset_page_size = max_asset_page_size

    @classmethod
    def from_settings(cls, runtime_settings: Settings) -> "JumpServerClient":
        return cls(
            httpx.AsyncClient(
                base_url=str(runtime_settings.jumpserver_url).rstrip("/"),
                auth=JumpServerSignatureAuth(
                    runtime_settings.access_key_id,
                    runtime_settings.access_key_secret,
                    runtime_settings.jms_org,
                ),
                verify=runtime_settings.verify_tls,
                timeout=runtime_settings.request_timeout_seconds,
                headers={"Accept": "application/json"},
            ),
            runtime_settings.max_asset_page_size,
        )

    async def __aenter__(self) -> "JumpServerClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def get_health(self) -> dict[str, Any]:
        return await self._get_json("/api/health/")

    async def list_assets(self, search: str | None, limit: int, offset: int) -> dict[str, Any]:
        if limit < 1 or limit > self._max_asset_page_size:
            raise ValueError(f"limit must be between 1 and {self._max_asset_page_size}")
        if offset < 0:
            raise ValueError("offset must be zero or greater")
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if search and search.strip():
            params["search"] = search.strip()
        return await self._get_json("/api/v1/assets/assets/", params=params)

    async def get_asset(self, asset_id: str) -> dict[str, Any]:
        asset_uuid = UUID(asset_id)
        return await self._get_json(f"/api/v1/assets/assets/{asset_uuid}/")

    async def _get_json(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> dict[str, Any]:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"data": payload}
