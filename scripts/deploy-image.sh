#!/usr/bin/env bash
set -euo pipefail

: "${JMS_MCP_IMAGE:?JMS_MCP_IMAGE is required}"
: "${HARBOR_REGISTRY:?HARBOR_REGISTRY is required}"
: "${HARBOR_PULL_SECRET_ARN:?HARBOR_PULL_SECRET_ARN is required}"

deploy_root=/opt/jms-mcp
compose_file="$deploy_root/compose.production.yaml"

test -f "$compose_file" || { echo "Missing production compose file: $compose_file" >&2; exit 1; }
command -v aws >/dev/null || { echo "aws CLI is required on the EC2 host" >&2; exit 1; }
command -v docker >/dev/null || { echo "docker is required on the EC2 host" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required on the EC2 host" >&2; exit 1; }

secret_json=$(aws secretsmanager get-secret-value \
  --secret-id "$HARBOR_PULL_SECRET_ARN" \
  --query SecretString \
  --output text)
readarray -t registry_credentials < <(
  python3 -c 'import json, sys; value = json.load(sys.stdin); print(value["username"]); print(value["password"])' \
    <<<"$secret_json"
)
test "${#registry_credentials[@]}" -eq 2 || { echo "Invalid Harbor pull secret" >&2; exit 1; }

printf '%s' "${registry_credentials[1]}" | docker login "$HARBOR_REGISTRY" \
  --username "${registry_credentials[0]}" --password-stdin >/dev/null
unset secret_json registry_credentials

cd "$deploy_root"
export JMS_MCP_IMAGE
docker compose -f "$compose_file" pull
docker compose -f "$compose_file" up -d --no-build --remove-orphans

curl --fail --silent --show-error --retry 12 --retry-connrefused --retry-delay 2 \
  http://127.0.0.1:8099/healthz >/dev/null
docker image inspect "$JMS_MCP_IMAGE" --format '{{index .RepoDigests 0}}'
echo "Deployment completed for $JMS_MCP_IMAGE"
