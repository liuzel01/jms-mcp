"""Default-deny policy for OpenAPI operations exposed as MCP tools."""

from collections.abc import Iterable, Mapping
from typing import Any

import mcp.types as types


READ_ONLY_METHODS = frozenset({"get", "head"})


class ToolPolicyError(ValueError):
    """Raised when an enabled MCP operation violates the server policy."""


def parse_operation_allowlist(value: str) -> set[str]:
    """Parse a comma-separated operationId allowlist from configuration."""
    return {operation.strip() for operation in value.split(",") if operation.strip()}


def select_read_only_tools(
    all_tools: Iterable[types.Tool],
    operation_map: Mapping[str, Mapping[str, Any]],
    enabled_operations: set[str],
) -> tuple[list[types.Tool], dict[str, dict[str, Any]]]:
    """Return only explicitly enabled GET/HEAD tools and their operations.

    The OpenAPI converter creates a tool for every Swagger operation.  This
    policy deliberately treats that output as untrusted inventory: a tool is
    exposed only when its operationId is configured and its HTTP method is
    intrinsically read-only.
    """
    if not enabled_operations:
        raise ToolPolicyError("MCP_TOOL_ALLOWLIST must contain at least one operationId")

    unknown_operations = enabled_operations.difference(operation_map)
    if unknown_operations:
        unknown = ", ".join(sorted(unknown_operations))
        raise ToolPolicyError(f"Configured operationId is absent from Swagger: {unknown}")

    selected_operations: dict[str, dict[str, Any]] = {}
    for operation_id in enabled_operations:
        operation = dict(operation_map[operation_id])
        method = str(operation.get("method", "")).lower()
        if method not in READ_ONLY_METHODS:
            raise ToolPolicyError(
                f"Configured operationId is not read-only ({method.upper()}): {operation_id}"
            )
        selected_operations[operation_id] = operation

    selected_tools = []
    for tool in all_tools:
        if tool.name in selected_operations:
            selected_tools.append(
                tool.model_copy(
                    update={
                        "annotations": types.ToolAnnotations(
                            readOnlyHint=True,
                            destructiveHint=False,
                            idempotentHint=True,
                            openWorldHint=False,
                        )
                    }
                )
            )

    missing_tools = enabled_operations.difference(tool.name for tool in selected_tools)
    if missing_tools:
        missing = ", ".join(sorted(missing_tools))
        raise ToolPolicyError(f"Configured operationId has no MCP tool: {missing}")

    return selected_tools, selected_operations
