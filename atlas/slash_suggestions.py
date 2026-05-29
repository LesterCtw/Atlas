from __future__ import annotations

from collections.abc import Sequence


class SlashSuggestionState:
    def __init__(self) -> None:
        self.options: list[str] = []
        self.selected_index = 0

    @property
    def has_options(self) -> bool:
        return bool(self.options)

    def update(self, options: Sequence[str]) -> None:
        self.options = list(options)
        if not self.options:
            self.selected_index = 0
            return
        self.selected_index = min(self.selected_index, len(self.options) - 1)

    def clear(self) -> None:
        self.options = []
        self.selected_index = 0

    def selected(self) -> str | None:
        if not self.options:
            return None
        return self.options[self.selected_index]

    def move_selection(self, direction: int) -> None:
        if not self.options:
            return
        self.selected_index = (self.selected_index + direction) % len(self.options)
