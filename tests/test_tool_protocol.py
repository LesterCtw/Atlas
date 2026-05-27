from __future__ import annotations

import unittest

from atlas.tool_protocol import ToolCall, ToolCallError, parse_tool_call


class ToolProtocolTests(unittest.TestCase):
    def test_parses_one_valid_fenced_json_tool_call(self) -> None:
        model_response = """I need to inspect the workspace.

```json
{
  "type": "atlas.tool_call",
  "tool": "echo",
  "args": {"text": "hello"}
}
```
"""

        result = parse_tool_call(model_response)

        self.assertEqual(result, ToolCall(tool="echo", args={"text": "hello"}))

    def test_rejects_malformed_json_with_retry_message(self) -> None:
        model_response = """```json
{
  "type": "atlas.tool_call",
  "tool": "echo",
  "args": {"text": "hello"
}
```"""

        result = parse_tool_call(model_response)

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "malformed-json")
        self.assertIn("valid JSON", result.message)

    def test_rejects_unknown_tool_name(self) -> None:
        model_response = """```json
{
  "type": "atlas.tool_call",
  "tool": "missing",
  "args": {}
}
```"""

        result = parse_tool_call(model_response, available_tools={"echo"})

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "unknown-tool")
        self.assertIn("missing", result.message)

    def test_rejects_missing_args(self) -> None:
        model_response = """```json
{
  "type": "atlas.tool_call",
  "tool": "echo"
}
```"""

        result = parse_tool_call(model_response, available_tools={"echo"})

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "missing-args")
        self.assertIn("args", result.message)

    def test_rejects_missing_tool_name(self) -> None:
        model_response = """```json
{
  "type": "atlas.tool_call",
  "args": {}
}
```"""

        result = parse_tool_call(model_response, available_tools={"echo"})

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "missing-tool")
        self.assertIn("tool", result.message)

    def test_rejects_args_that_are_not_an_object(self) -> None:
        model_response = """```json
{
  "type": "atlas.tool_call",
  "tool": "echo",
  "args": ["hello"]
}
```"""

        result = parse_tool_call(model_response, available_tools={"echo"})

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "invalid-args")
        self.assertIn("object", result.message)

    def test_rejects_multiple_tool_calls_in_one_response(self) -> None:
        model_response = """```json
{"type": "atlas.tool_call", "tool": "echo", "args": {"text": "one"}}
```

```json
{"type": "atlas.tool_call", "tool": "echo", "args": {"text": "two"}}
```"""

        result = parse_tool_call(model_response, available_tools={"echo"})

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "multiple-tool-calls")
        self.assertIn("single", result.message)


if __name__ == "__main__":
    unittest.main()
