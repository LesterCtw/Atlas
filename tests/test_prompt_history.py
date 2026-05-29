from __future__ import annotations

import unittest

from atlas.prompt_history import PromptHistory


class PromptHistoryTests(unittest.TestCase):
    def test_browses_recent_prompts_and_returns_to_blank(self) -> None:
        history = PromptHistory()
        history.remember("first prompt")
        history.remember("second prompt")

        self.assertEqual(history.move(-1), "second prompt")
        self.assertEqual(history.move(-1), "first prompt")
        self.assertEqual(history.move(1), "second prompt")
        self.assertEqual(history.move(1), "")

    def test_down_key_without_active_history_does_nothing(self) -> None:
        history = PromptHistory()
        history.remember("first prompt")

        self.assertIsNone(history.move(1))

    def test_non_empty_draft_does_not_start_history_browse(self) -> None:
        history = PromptHistory()
        history.remember("first prompt")

        self.assertFalse(history.should_restore("draft"))
        self.assertTrue(history.should_restore(""))

    def test_manual_input_change_resets_history_browse(self) -> None:
        history = PromptHistory()
        history.remember("first prompt")
        self.assertEqual(history.move(-1), "first prompt")

        history.handle_input_changed()

        self.assertFalse(history.is_browsing)

    def test_programmatic_input_change_preserves_history_browse(self) -> None:
        history = PromptHistory()
        history.remember("first prompt")
        self.assertEqual(history.move(-1), "first prompt")

        history.record_programmatic_change()
        history.handle_input_changed()

        self.assertTrue(history.is_browsing)


if __name__ == "__main__":
    unittest.main()
