# JumpServer Operations MCP

Production-oriented, read-only MCP server for daily JumpServer operations.

This is not a Swagger-to-MCP gateway. Every MCP tool is implemented in source,
uses a fixed `GET` endpoint, and is marked read-only. The server contains no
generic HTTP tool and cannot expose a newly added Swagger API automatically.

## Current tools

- `get_jumpserver_health` — JumpServer, database, and Redis health.
- `list_jumpserver_assets` — bounded, optionally searched asset inventory.
- `get_jumpserver_asset` — one asset's details, addressed by UUID.

The configured JumpServer system user remains the final authorization boundary.
Grant it the narrowest read-only RBAC permissions needed for these tools.

## Configuration

Create a local `.env` file; never commit it.

```dotenv
server_port=8099
jumpserver_url=https://jumpserver.example
access_key_id=replace-with-system-user-access-key-id
access_key_secret=replace-with-system-user-access-key-secret
jms_org=00000000-0000-0000-0000-000000000002

# Random MCP entry credential, at least 32 characters.
api_key=replace-with-a-random-entry-key-of-at-least-32-characters

# Set false only for a deliberately accepted private CA / test exception.
verify_tls=true
request_timeout_seconds=30
max_asset_page_size=100
```

## Run locally

```bash
uv run main.py
```

The Streamable HTTP MCP endpoint is `http://127.0.0.1:8099/mcp`; liveness is
available without contacting JumpServer at `/healthz`.

```json
{
  "type": "streamable_http",
  "url": "http://127.0.0.1:8099/mcp",
  "headers": { "Authorization": "Bearer <api_key>" }
}
```

## Adding a tool

Adding an operation requires a source change, tests, and review. Keep each tool
read-only and bounded; do not add a generic Swagger/OpenAPI conversion route or
a generic proxy tool. CI/CD deployment will be introduced separately through
GitHub Actions; this repository does not use manual production copy/deploy
commands as its release mechanism.
