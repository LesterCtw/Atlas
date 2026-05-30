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


if __name__ == "__main__":
    unittest.main()
