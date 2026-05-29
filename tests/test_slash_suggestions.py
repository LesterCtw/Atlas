from __future__ import annotations

import unittest

from atlas.slash_suggestions import SlashSuggestionState


class SlashSuggestionStateTests(unittest.TestCase):
    def test_selects_current_option(self) -> None:
        suggestions = SlashSuggestionState()

        suggestions.update(["/help", "/exit"])

        self.assertTrue(suggestions.has_options)
        self.assertEqual(suggestions.selected(), "/help")

    def test_moves_selection_with_wraparound(self) -> None:
        suggestions = SlashSuggestionState()
        suggestions.update(["/help", "/exit"])

        suggestions.move_selection(-1)
        self.assertEqual(suggestions.selected(), "/exit")

        suggestions.move_selection(1)
        self.assertEqual(suggestions.selected(), "/help")

    def test_update_clamps_existing_selection(self) -> None:
        suggestions = SlashSuggestionState()
        suggestions.update(["/help", "/exit", "/llm-wiki"])
        suggestions.move_selection(-1)

        suggestions.update(["/help"])

        self.assertEqual(suggestions.selected_index, 0)
        self.assertEqual(suggestions.selected(), "/help")

    def test_clear_removes_selection(self) -> None:
        suggestions = SlashSuggestionState()
        suggestions.update(["/help"])

        suggestions.clear()

        self.assertFalse(suggestions.has_options)
        self.assertIsNone(suggestions.selected())
        self.assertEqual(suggestions.selected_index, 0)


if __name__ == "__main__":
    unittest.main()
