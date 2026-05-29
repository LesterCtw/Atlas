from __future__ import annotations

import unittest

from atlas.json_fences import (
    JsonFencePayloadError,
    MalformedJsonFenceError,
    MissingJsonFenceError,
    find_json_fence_contents,
    format_json_fence,
    load_json_fence_content,
    parse_first_json_fence_object,
)


class JsonFencesTests(unittest.TestCase):
    def test_finds_all_json_fence_contents(self) -> None:
        text = """Before.

```json
{"a": 1}
```

Between.

```json
{"b": 2}
```
"""

        self.assertEqual(find_json_fence_contents(text), ('{"a": 1}\n', '{"b": 2}\n'))

    def test_loads_json_fence_content(self) -> None:
        self.assertEqual(load_json_fence_content('{"ok": true}'), {"ok": True})

    def test_rejects_malformed_json_content(self) -> None:
        with self.assertRaises(MalformedJsonFenceError):
            load_json_fence_content('{"ok": true')

    def test_parses_first_json_fence_object(self) -> None:
        text = """```json
{"kind": "first"}
```

```json
{"kind": "second"}
```"""

        self.assertEqual(parse_first_json_fence_object(text), {"kind": "first"})

    def test_rejects_missing_json_fence(self) -> None:
        with self.assertRaises(MissingJsonFenceError):
            parse_first_json_fence_object("{}")

    def test_rejects_non_object_first_payload(self) -> None:
        with self.assertRaises(JsonFencePayloadError):
            parse_first_json_fence_object("```json\n[]\n```")

    def test_formats_json_fence(self) -> None:
        self.assertEqual(
            format_json_fence({"type": "atlas.tool_result", "result": "ok"}),
            """```json
{
  "type": "atlas.tool_result",
  "result": "ok"
}
```""",
        )


if __name__ == "__main__":
    unittest.main()
