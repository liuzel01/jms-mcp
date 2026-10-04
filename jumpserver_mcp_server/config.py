from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
    )
    server_port: int = 8099
    api_key: str = ''
    api_base_url:str = ''
    api_token:str=  ''
    access_key_id: str = ''
    access_key_secret: str = ''
    jms_org: str = '00000000-0000-0000-0000-000000000002'
    base_path: str = '/sse'
    http_base_path: str = '/mcp'
    # Comma-separated OpenAPI operationIds. Only GET/HEAD operations are accepted.
    mcp_tool_allowlist: str = 'api_health_retrieve'
    swagger_url: str = ''
    log_level: str = 'INFO'
    debug: bool = False
    jumpserver_url: str = ''


settings = Settings()
