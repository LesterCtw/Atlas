from __future__ import annotations


class PromptHistory:
    def __init__(self) -> None:
        self._entries: list[str] = []
        self._index: int | None = None
        self._programmatic_changes = 0

    @property
    def is_browsing(self) -> bool:
        return self._index is not None

    def remember(self, prompt: str) -> None:
        self._entries.append(prompt)
        self.reset_browse()

    def reset_browse(self) -> None:
        self._index = None

    def should_restore(self, prompt_value: str) -> bool:
        return not prompt_value.strip() or self.is_browsing

    def move(self, direction: int) -> str | None:
        if not self._entries:
            return None

        if self._index is None:
            if direction > 0:
                return None
            self._index = len(self._entries) - 1
        else:
            next_index = self._index + direction
            if next_index >= len(self._entries):
                self._index = None
                return ""
            self._index = max(0, next_index)

        return self._entries[self._index]

    def record_programmatic_change(self) -> None:
        self._programmatic_changes += 1

    def handle_input_changed(self) -> None:
        if self._programmatic_changes:
            self._programmatic_changes -= 1
            return
        self.reset_browse()
