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

# Comma-separated public MCP Host header values. Keep DNS rebinding protection enabled.
mcp_allowed_hosts=10.100.166.109:8099
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

## CI/CD production configuration

`.github/workflows/ci-cd.yml` tests pull requests, then builds a Linux AMD64
image for `main`, pushes `sha-<commit>` to Harbor, and deploys the pushed digest
through AWS Systems Manager. GitHub's `production` Environment should require
review before its build and deploy jobs run.

Configure these GitHub Environment values before enabling a production release:

| Type | Name | Purpose |
| --- | --- | --- |
| Variable | `HARBOR_REGISTRY` | Harbor host and optional port, without a scheme. |
| Variable | `HARBOR_PROJECT` | Harbor project that holds `jms-mcp`. |
| Variable | `DEPLOY_AWS_REGION` | AWS Region containing the target EC2 instance. |
| Variable | `DEPLOY_EC2_INSTANCE_ID` | SSM-managed EC2 instance ID. |
| Variable | `HARBOR_PULL_SECRET_ARN` | Secrets Manager ARN holding the EC2 pull credential. |
| Variable | `MCP_ALLOWED_HOSTS` | Comma-separated public MCP Host header values, including port. |
| Secret | `HARBOR_ROBOT_ACCOUNT` | Harbor CI robot account with project push/pull permission. |
| Secret | `HARBOR_ROBOT_ACCOUNT_TOKEN` | Harbor CI robot account token. |
| Secret | `DEPLOY_AWS_ROLE_ARN` | OIDC-assumable deployment role ARN. |

The `HARBOR_PULL_SECRET_ARN` value must refer to a Secrets Manager JSON secret
with exactly `username` and `password` fields. The EC2 instance profile needs
only `secretsmanager:GetSecretValue` for that ARN. Its Harbor robot account
needs only pull access; it is retrieved at deployment time and is never stored
in the repository or sent from GitHub Actions. The deployment script uses a
temporary Docker credential directory and removes it on exit.

The GitHub OIDC deployment role needs only `ssm:SendCommand`,
`ssm:GetCommandInvocation`, and related SSM read/wait actions for the named
instance. Scope the OIDC trust policy to this repository and the `production`
Environment. The release command writes the repository-controlled
`compose.production.yaml`, preserves `/opt/jms-mcp/.env`, pulls the exact image
digest, and verifies `/healthz`.
