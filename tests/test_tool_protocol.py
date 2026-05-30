from __future__ import annotations

import unittest

from atlas.tool_protocol import ToolBatch, ToolBatchCall, ToolCall, ToolCallError, parse_tool_call


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

    def test_parses_plain_json_tool_call_after_markdown_rendering_removed_fence(self) -> None:
        model_response = """I need to inspect the workspace.

JSON
{
  "type": "atlas.tool_call",
  "tool": "echo",
  "args": {"text": "hello"}
}
"""

        result = parse_tool_call(model_response)

        self.assertEqual(result, ToolCall(tool="echo", args={"text": "hello"}))

    def test_plain_json_tool_call_preserves_nested_args(self) -> None:
        model_response = """JSON
{
  "type": "atlas.tool_call",
  "tool": "file.write",
  "args": {
    "path": "notes.json",
    "content": "{\\"nested\\": {\\"ok\\": true}}",
    "metadata": {"source": {"id": "case-1"}}
  }
}
"""

        result = parse_tool_call(model_response)

        self.assertEqual(
            result,
            ToolCall(
                tool="file.write",
                args={
                    "path": "notes.json",
                    "content": '{"nested": {"ok": true}}',
                    "metadata": {"source": {"id": "case-1"}},
                },
            ),
        )

    def test_parses_read_only_tool_batch(self) -> None:
        model_response = """```json
{
  "type": "atlas.tool_batch",
  "calls": [
    {
      "id": "list-root",
      "tool": "file.list",
      "args": {"path": "."}
    },
    {
      "id": "read-readme",
      "tool": "file.read",
      "args": {"path": "README.md"}
    }
  ]
}
```"""

        result = parse_tool_call(
            model_response,
            available_tools={"file.list", "file.read", "file.write"},
            batch_tools={"file.list", "file.read"},
        )

        self.assertEqual(
            result,
            ToolBatch(
                calls=(
                    ToolBatchCall(id="list-root", tool="file.list", args={"path": "."}),
                    ToolBatchCall(id="read-readme", tool="file.read", args={"path": "README.md"}),
                )
            ),
        )

    def test_plain_malformed_tool_call_returns_retry_error(self) -> None:
        model_response = """JSON
{
  "type": "atlas.tool_call",
  "tool": "echo",
  "args": {"text": "hello"
"""

        result = parse_tool_call(model_response)

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "malformed-json")

    def test_plain_malformed_outer_tool_call_does_not_get_hidden_by_inner_args_object(self) -> None:
        model_response = """JSON
{
  "type": "atlas.tool_call",
  "tool": "echo",
  "args": {"text": "hello"}
"""

        result = parse_tool_call(model_response)

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "malformed-json")

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

    def test_rejects_removed_pdf_attach_tool_name(self) -> None:
        removed_tool_name = "pdf" + ".attach"
        model_response = f"""```json
{{
  "type": "atlas.tool_call",
  "tool": "{removed_tool_name}",
  "args": {{"path": "docs/case.pdf"}}
}}
```"""

        result = parse_tool_call(model_response, available_tools={"file.attach"})

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "unknown-tool")
        self.assertIn(removed_tool_name, result.message)

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

    def test_rejects_tool_name_that_is_not_a_string(self) -> None:
        model_response = """```json
{
  "type": "atlas.tool_call",
  "tool": 123,
  "args": {}
}
```"""

        result = parse_tool_call(model_response, available_tools={"echo"})

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "invalid-tool")
        self.assertIn("tool name", result.message)

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

    def test_rejects_tool_batch_larger_than_limit(self) -> None:
        calls = ",\n".join(
            f'{{"id": "read-{index}", "tool": "file.read", "args": {{"path": "{index}.md"}}}}'
            for index in range(6)
        )
        model_response = f"""```json
{{"type": "atlas.tool_batch", "calls": [{calls}]}}
```"""

        result = parse_tool_call(
            model_response,
            available_tools={"file.read"},
            batch_tools={"file.read"},
        )

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "batch-too-large")
        self.assertIn("at most 5", result.message)

    def test_rejects_side_effect_tool_in_batch(self) -> None:
        model_response = """```json
{
  "type": "atlas.tool_batch",
  "calls": [
    {
      "id": "write-notes",
      "tool": "file.write",
      "args": {"path": "notes.md", "content": "hello"}
    }
  ]
}
```"""

        result = parse_tool_call(
            model_response,
            available_tools={"file.read", "file.write"},
            batch_tools={"file.read"},
        )

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "batch-tool-not-allowed")
        self.assertIn("file.write", result.message)

    def test_rejects_duplicate_batch_call_ids(self) -> None:
        model_response = """```json
{
  "type": "atlas.tool_batch",
  "calls": [
    {"id": "read", "tool": "file.read", "args": {"path": "a.md"}},
    {"id": "read", "tool": "file.read", "args": {"path": "b.md"}}
  ]
}
```"""

        result = parse_tool_call(
            model_response,
            available_tools={"file.read"},
            batch_tools={"file.read"},
        )

        self.assertIsInstance(result, ToolCallError)
        self.assertEqual(result.code, "duplicate-batch-call-id")


if __name__ == "__main__":
    unittest.main()
