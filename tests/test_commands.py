from __future__ import annotations

import unittest

from atlas.commands import handle_slash_command


class SlashCommandTests(unittest.TestCase):
    def test_help_command_lists_available_commands(self) -> None:
        result = handle_slash_command("/help")

        self.assertEqual(result.action, "message")
        self.assertIn("/help", result.message)
        self.assertIn("/exit", result.message)

    def test_exit_command_requests_clean_exit(self) -> None:
        result = handle_slash_command("/exit")

        self.assertEqual(result.action, "exit")
        self.assertIn("結束", result.message)

    def test_unknown_slash_command_returns_clear_error(self) -> None:
        result = handle_slash_command("/missing")

        self.assertEqual(result.action, "message")
        self.assertIn("未知命令", result.message)
        self.assertIn("/missing", result.message)


if __name__ == "__main__":
    unittest.main()
