# JumpServer MCP Server

## Production safety boundary

JumpServer Swagger is used only to build a local inventory of operations. It is
**not** automatically exposed as a full MCP tool set. By default this server
exposes only `api_health_retrieve`.

To enable an additional operation, add its exact Swagger `operationId` to the
comma-separated allowlist and restart the service:

```txt
# Only GET and HEAD operations are permitted. POST, PUT, PATCH and DELETE
# operationIds cause startup to fail.
mcp_tool_allowlist=api_health_retrieve,assets_list
```

Use a least-privilege JumpServer system user/API key. Adding a read operation
can still expose sensitive data to every MCP client authorized to use this
server, so review the operation's response fields and the system user's RBAC
before enabling it. The server marks allowed tools as read-only in MCP metadata.

## Configure JumpServer Environment File (.env)

```txt
# Bearer token to access the JumpServer Swagger Json API, optional
api_token=xxxxxxx 
jumpserver_url=http://jumpserverhost

# Optional: Access Key authentication (recommended over a long-lived user token)
access_key_id=xxxxxxx
access_key_secret=xxxxxxx
jms_org=00000000-0000-0000-0000-000000000002

# MCP entry-point bearer key and explicit read-only operation allowlist
api_key=replace-with-a-random-secret
mcp_tool_allowlist=api_health_retrieve
```

## Start Docker Container

```bash
docker run -d -it -p 8099:8099 --env-file .env --name jms_mcp ghcr.io/jumpserver/mcp:latest
```

## Create JumpServer API Bearer Token for MCP Server

```shell

TOKEN=$(curl -s -X POST http://jumpserver_host/api/v1/authentication/auth/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "xxxx"
  }' \
  --insecure | jq -r '.token')

echo "Your Bearer token: $TOKEN"

```


## MCP Server Configuration

```json
{
    "type": "streamable_http",
    "url": "http://127.0.0.1:8099/mcp",
    "headers": {
        "Authorization": "Bearer xxxxxxxx"
    }
}
```

Legacy SSE remains available at `/sse` for clients that require it. New clients
should use the streamable HTTP endpoint at `/mcp`.
