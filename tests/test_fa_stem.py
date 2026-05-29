from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.fa_stem import FaStemBriefError, parse_fa_stem_circle, select_single_stem_image


class FaStemBriefTests(unittest.TestCase):
    def test_parse_fenced_json_circle_response(self) -> None:
        circle = parse_fa_stem_circle(
            """The suggested mark is:
```json
{
  "center_x_percent": 25,
  "center_y_percent": 40,
  "radius_percent": 12,
  "reason": "Void-like contrast near the via edge.",
  "confidence": "medium"
}
```"""
        )

        self.assertEqual(circle.center_x_percent, 25.0)
        self.assertEqual(circle.center_y_percent, 40.0)
        self.assertEqual(circle.radius_percent, 12.0)
        self.assertEqual(circle.reason, "Void-like contrast near the via edge.")
        self.assertEqual(circle.confidence, "medium")

    def test_parse_rejects_malformed_or_incomplete_json(self) -> None:
        cases = {
            "missing-fence": ("{}", "fenced JSON"),
            "malformed-json": ("```json\n{\"center_x_percent\": 25\n```", "malformed JSON"),
            "missing-field": (
                """```json
{"center_x_percent": 25, "center_y_percent": 40, "reason": "x", "confidence": "low"}
```""",
                "radius_percent",
            ),
        }

        for case_name, (response, expected_error) in cases.items():
            with self.subTest(case_name=case_name):
                with self.assertRaisesRegex(FaStemBriefError, expected_error):
                    parse_fa_stem_circle(response)

    def test_select_single_stem_image_uses_deterministic_order(self) -> None:
        with TemporaryDirectory() as directory:
            case_folder = Path(directory)
            (case_folder / "z-later.jpeg").write_bytes(b"fake jpeg")
            (case_folder / "notes.txt").write_text("ignore", encoding="utf-8")
            selected_image = case_folder / "a-first.jpg"
            selected_image.write_bytes(b"fake jpg")

            selected = select_single_stem_image(case_folder)

        self.assertEqual(selected, selected_image.resolve())


if __name__ == "__main__":
    unittest.main()
