import unittest

import mcp.types as types

from jumpserver_mcp_server.tool_policy import (
    ToolPolicyError,
    parse_operation_allowlist,
    select_read_only_tools,
)


def tool(name: str) -> types.Tool:
    return types.Tool(name=name, description=name, inputSchema={"type": "object"})


class ToolPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tools = [tool("api_health_retrieve"), tool("users_list"), tool("users_create")]
        self.operation_map = {
            "api_health_retrieve": {"method": "get", "path": "/api/health/"},
            "users_list": {"method": "head", "path": "/api/users/"},
            "users_create": {"method": "post", "path": "/api/users/"},
        }

    def test_selects_only_explicit_read_only_tools(self) -> None:
        tools, operations = select_read_only_tools(
            self.tools, self.operation_map, {"api_health_retrieve", "users_list"}
        )

        self.assertEqual([item.name for item in tools], ["api_health_retrieve", "users_list"])
        self.assertEqual(set(operations), {"api_health_retrieve", "users_list"})
        self.assertTrue(tools[0].annotations.readOnlyHint)
        self.assertFalse(tools[0].annotations.destructiveHint)

    def test_rejects_write_operation_even_when_explicitly_configured(self) -> None:
        with self.assertRaisesRegex(ToolPolicyError, "not read-only \(POST\)"):
            select_read_only_tools(self.tools, self.operation_map, {"users_create"})

    def test_rejects_unknown_operation(self) -> None:
        with self.assertRaisesRegex(ToolPolicyError, "absent from Swagger"):
            select_read_only_tools(self.tools, self.operation_map, {"does_not_exist"})

    def test_parses_trimmed_comma_separated_allowlist(self) -> None:
        self.assertEqual(
            parse_operation_allowlist(" api_health_retrieve, users_list ,"),
            {"api_health_retrieve", "users_list"},
        )


if __name__ == "__main__":
    unittest.main()
