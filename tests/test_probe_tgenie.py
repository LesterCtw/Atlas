from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]


def load_probe_module() -> ModuleType:
    module_path = ROOT / "scripts" / "probe_tgenie.py"
    spec = importlib.util.spec_from_file_location("probe_tgenie", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load probe_tgenie.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProbeTgenieTests(unittest.TestCase):
    def test_probe_tracks_issue_5_targets_and_observations(self) -> None:
        probe = load_probe_module()

        target_keys = [key for key, _description in probe.TARGETS]
        observation_keys = [key for key, _description in probe.OBSERVATIONS]

        self.assertIn("latest_response", target_keys)
        self.assertIn("target_model", observation_keys)
        self.assertIn("stop_generating_hover_label", observation_keys)
        self.assertIn("latest_response_text", observation_keys)
        self.assertIn("smoke_result", observation_keys)
        self.assertEqual(probe.SMOKE_PROMPT, "Atlas smoke test. Reply with exactly: atlas-ok")

    def test_probe_prefers_stable_candidate_when_raw_selector_is_manual_review(self) -> None:
        probe = load_probe_module()
        element = {
            "tag": "svg",
            "role": "",
            "type": "",
            "text": "",
            "ariaLabel": "",
            "placeholder": "",
            "label": "",
            "title": "",
            "testId": "",
            "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
        }
        stable_probe = {
            "selector_candidates": [
                {
                    "method": "get_by_role",
                    "role": "button",
                    "name": "Open sidebar",
                    "reason": "ancestor depth 1 button name",
                }
            ]
        }

        hint = probe.choose_selector_hint(element, stable_probe)

        self.assertEqual(hint["method"], "get_by_role")
        self.assertEqual(hint["role"], "button")
        self.assertEqual(hint["name"], "Open sidebar")

    def test_probe_report_includes_issue_5_observations_and_text_blocks(self) -> None:
        probe = load_probe_module()

        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            elements = [
                {
                    "tag": "button",
                    "role": "",
                    "type": "",
                    "text": "",
                    "ariaLabel": "",
                    "placeholder": "",
                    "label": "",
                    "title": "",
                    "testId": "",
                    "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
                }
            ]
            text_blocks = [
                {
                    "tag": "div",
                    "role": "",
                    "text": "atlas-ok",
                    "ariaLabel": "",
                    "placeholder": "",
                    "title": "",
                    "id": "",
                    "testId": "",
                    "bbox": {"x": 5, "y": 6, "width": 7, "height": 8},
                }
            ]
            choices = {
                "latest_response": {
                    "index": 0,
                    "source": "text_block",
                    "description": "最新 tGenie assistant 回覆文字區",
                    "element": text_blocks[0],
                    "selector_hint": {"method": "text_contains", "value": "atlas-ok"},
                }
            }
            observations = {
                "target_model": "Gemini-3.1-Pro Preview",
                "latest_response_text": "atlas-ok",
                "smoke_result": "success",
            }

            json_path, md_path = probe.write_report(
                output_dir=output_dir,
                url="https://tgenie.example.test",
                elements=elements,
                choices=choices,
                observations=observations,
                text_blocks=text_blocks,
                action_log=[],
                screenshot_path=None,
            )

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            report = md_path.read_text(encoding="utf-8")

            self.assertEqual(payload["observations"]["target_model"], "Gemini-3.1-Pro Preview")
            self.assertEqual(payload["text_blocks"][0]["text"], "atlas-ok")
            self.assertIn("## #5 必填觀察", report)
            self.assertIn("Gemini-3.1-Pro Preview", report)
            self.assertIn("latest_response", report)
            self.assertIn("atlas-ok", report)

    def test_probe_report_includes_stable_selector_candidates(self) -> None:
        probe = load_probe_module()

        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            elements = [
                {
                    "tag": "svg",
                    "role": "",
                    "type": "",
                    "text": "",
                    "ariaLabel": "",
                    "placeholder": "",
                    "label": "",
                    "title": "",
                    "testId": "",
                    "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
                }
            ]
            stable_probe = {
                "nearest_interactive": {
                    "tag": "button",
                    "role": "",
                    "title": "Open sidebar",
                    "ariaLabel": "",
                    "text": "",
                },
                "selector_candidates": [
                    {
                        "method": "get_by_title",
                        "value": "Open sidebar",
                        "reason": "ancestor depth 1 title",
                    }
                ],
            }
            choices = {
                "sidebar_toggle": {
                    "index": 0,
                    "description": "側邊欄展開/收合按鈕",
                    "element": elements[0],
                    "raw_selector_hint": {"method": "manual_review", "value": "(no visible label)"},
                    "selector_hint": {"method": "get_by_title", "value": "Open sidebar"},
                    "stable_probe": stable_probe,
                }
            }

            _json_path, md_path = probe.write_report(
                output_dir=output_dir,
                url="https://tgenie.example.test",
                elements=elements,
                choices=choices,
                observations={},
                text_blocks=[],
                action_log=[],
                screenshot_path=None,
            )

            report = md_path.read_text(encoding="utf-8")

            self.assertIn("Stable selector candidates", report)
            self.assertIn("get_by_title('Open sidebar')", report)
            self.assertIn("Nearest interactive", report)


if __name__ == "__main__":
    unittest.main()
