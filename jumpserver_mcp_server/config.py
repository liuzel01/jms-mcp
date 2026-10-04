"""Runtime configuration and entry-point authentication."""

import hmac

from pydantic import Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    server_port: int = Field(default=8099, ge=1, le=65535)
    jumpserver_url: HttpUrl
    access_key_id: str = Field(min_length=1)
    access_key_secret: str = Field(min_length=1)
    jms_org: str = "00000000-0000-0000-0000-000000000002"
    api_key: str = Field(min_length=32)
    verify_tls: bool = True
    request_timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_asset_page_size: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def reject_missing_api_key(self) -> "Settings":
        if not self.api_key.strip():
            raise ValueError("api_key must not be blank")
        return self

    def is_valid_entry_api_key(self, authorization: str | None) -> bool:
        expected = f"Bearer {self.api_key}"
        return authorization is not None and hmac.compare_digest(authorization, expected)


settings = Settings()
