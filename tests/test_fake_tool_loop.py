from __future__ import annotations

import unittest

from atlas.fake_loop import FakeTgenieAdapter, run_fake_tool_loop


class FakeToolLoopTests(unittest.TestCase):
    def test_fake_adapter_runs_one_tool_call_and_returns_next_model_response(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{"type": "atlas.tool_call", "tool": "echo", "args": {"text": "hello"}}
```""",
                "Final answer: hello",
            ]
        )

        result = run_fake_tool_loop(
            initial_prompt="say hello",
            adapter=adapter,
            tools={"echo": lambda args: {"text": args["text"]}},
        )

        self.assertEqual(result.final_response, "Final answer: hello")
        self.assertIn("parsing-tool-call", result.status_events)
        self.assertIn("executing-tool", result.status_events)
        self.assertIn("waiting-for-model", result.status_events)
        self.assertIn('"type": "atlas.tool_result"', adapter.sent_messages[1])
        self.assertIn('"text": "hello"', adapter.sent_messages[1])
        self.assertEqual(
            [event.kind for event in result.events],
            ["user_prompt", "assistant_tool_call", "tool_result", "assistant_final"],
        )
        self.assertEqual(result.events[0].message, "say hello")
        self.assertEqual(result.events[1].tool, "echo")
        self.assertEqual(result.events[1].args, {"text": "hello"})
        self.assertEqual(result.events[3].message, "Final answer: hello")

    def test_fake_adapter_runs_tool_batch_and_returns_next_model_response(self) -> None:
        adapter = FakeTgenieAdapter(
            responses=[
                """```json
{
  "type": "atlas.tool_batch",
  "calls": [
    {"id": "first", "tool": "echo", "args": {"text": "hello"}},
    {"id": "second", "tool": "echo", "args": {"text": "Atlas"}}
  ]
}
```""",
                "Final answer: hello Atlas",
            ]
        )

        result = run_fake_tool_loop(
            initial_prompt="say hello",
            adapter=adapter,
            tools={"echo": lambda args: {"text": args["text"]}},
        )

        self.assertEqual(result.final_response, "Final answer: hello Atlas")
        self.assertIn("executing-tool-batch", result.status_events)
        self.assertIn("sending-tool-batch-result", result.status_events)
        self.assertIn('"type": "atlas.tool_batch_result"', adapter.sent_messages[1])
        self.assertIn('"id": "first"', adapter.sent_messages[1])
        self.assertIn('"id": "second"', adapter.sent_messages[1])
        self.assertEqual(
            [event.kind for event in result.events],
            ["user_prompt", "assistant_tool_batch", "tool_batch_result", "assistant_final"],
        )


if __name__ == "__main__":
    unittest.main()
