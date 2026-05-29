from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from atlas.fa_stem import (
    FaStemBriefError,
    PhotoBundle,
    PhotoBundleTile,
    build_photo_bundle_prompt,
    collect_stem_images,
    create_photo_bundles,
    parse_fa_stem_circle,
    parse_photo_bundle_candidate_evidence,
    run_fa_stem_brief,
    select_single_stem_image,
)


class RecordingFaStemConversation:
    def __init__(self, response: str | list[str]) -> None:
        self.responses = [response] if isinstance(response, str) else list(response)
        self.attached_files: list[Path] = []
        self.prompts: list[str] = []

    async def attach_file(self, path: Path) -> None:
        self.attached_files.append(path)

    async def send_single_turn(self, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        return self.responses.pop(0)


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

    def test_collect_stem_images_recurses_and_uses_deterministic_order(self) -> None:
        with TemporaryDirectory() as directory:
            case_folder = Path(directory)
            nested = case_folder / "nested"
            nested.mkdir()
            (case_folder / "z-later.jpeg").write_bytes(b"fake jpeg")
            (case_folder / "notes.txt").write_text("ignore", encoding="utf-8")
            (case_folder / "panel.png").write_bytes(b"ignore png")
            (nested / "b-middle.JPG").write_bytes(b"fake jpg")
            (nested / "a-first.jpg").write_bytes(b"fake jpg")

            images = collect_stem_images(case_folder)

        self.assertEqual(
            [image.relative_to(case_folder.resolve()).as_posix() for image in images],
            [
                "nested/a-first.jpg",
                "nested/b-middle.JPG",
                "z-later.jpeg",
            ],
        )

    def test_create_photo_bundles_preserves_source_mapping_and_partial_batch(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            case_folder = workspace / "case-a"
            case_folder.mkdir()
            for index in range(10):
                image = Image.new("RGB", (32, 24), color=(index * 20, 20, 120))
                image.save(case_folder / f"stem-{index:02d}.jpg")

            images = collect_stem_images(case_folder)
            bundles = create_photo_bundles(
                workspace=workspace,
                case_folder=case_folder,
                images=images,
            )

            self.assertEqual(len(bundles), 2)
            self.assertTrue(bundles[0].path.name.endswith(".png"))
            self.assertTrue(bundles[0].path.exists())
            self.assertEqual(len(bundles[0].tiles), 9)
            self.assertEqual(len(bundles[1].tiles), 1)
            self.assertEqual(bundles[0].tiles[0].label, "A1")
            self.assertEqual(bundles[0].tiles[0].source_id, "case-a/stem-00.jpg")
            self.assertEqual(bundles[0].tiles[8].label, "C3")
            self.assertEqual(bundles[0].tiles[8].source_id, "case-a/stem-08.jpg")
            self.assertEqual(bundles[1].tiles[0].label, "A1")
            self.assertEqual(bundles[1].tiles[0].source_id, "case-a/stem-09.jpg")

    def test_build_photo_bundle_prompt_includes_mapping_and_candidate_instructions(self) -> None:
        bundle = PhotoBundle(
            path=Path("/tmp/photo-bundle-001.png"),
            tiles=(
                PhotoBundleTile(
                    label="A1",
                    source_id="case-a/stem-00.jpg",
                    source_path=Path("/tmp/stem-00.jpg"),
                ),
                PhotoBundleTile(
                    label="A2",
                    source_id="case-a/stem-01.jpg",
                    source_path=Path("/tmp/stem-01.jpg"),
                ),
            ),
        )

        prompt = build_photo_bundle_prompt(
            case_background="Leakage fails at VDD after stress.",
            bundle=bundle,
            batch_number=1,
            total_batches=2,
        )

        self.assertIn("senior semiconductor process failure analysis engineer", prompt)
        self.assertIn("Leakage fails at VDD after stress.", prompt)
        self.assertIn("Batch 1 of 2", prompt)
        self.assertIn("A1: case-a/stem-00.jpg", prompt)
        self.assertIn("A2: case-a/stem-01.jpg", prompt)
        self.assertIn("candidate observations", prompt)
        self.assertIn("not final conclusions", prompt)
        self.assertIn("candidate_observations", prompt)
        self.assertIn("tile_label", prompt)
        self.assertIn("observation", prompt)
        self.assertIn("inference", prompt)
        self.assertIn("uncertainty", prompt)
        self.assertIn("confidence", prompt)

    def test_parse_photo_bundle_candidate_evidence_maps_tiles_to_sources(self) -> None:
        bundle = PhotoBundle(
            path=Path("/tmp/photo-bundle-001.png"),
            tiles=(
                PhotoBundleTile(
                    label="A1",
                    source_id="case-a/stem-00.jpg",
                    source_path=Path("/tmp/stem-00.jpg"),
                ),
                PhotoBundleTile(
                    label="A2",
                    source_id="case-a/stem-01.jpg",
                    source_path=Path("/tmp/stem-01.jpg"),
                ),
            ),
        )

        evidence_items = parse_photo_bundle_candidate_evidence(
            """```json
{
  "candidate_observations": [
    {
      "tile_label": "A2",
      "observation": "Dark contrast appears near the via edge.",
      "inference": "This may indicate missing material.",
      "uncertainty": "The contrast may come from preparation.",
      "confidence": "medium",
      "coordinates": [
        {"center_x_percent": 25, "center_y_percent": 40, "radius_percent": 12}
      ]
    }
  ]
}
```""",
            bundle=bundle,
        )

        self.assertEqual(len(evidence_items), 1)
        self.assertEqual(evidence_items[0].source_id, "case-a/stem-01.jpg")
        self.assertEqual(evidence_items[0].observation, "Dark contrast appears near the via edge.")
        self.assertEqual(evidence_items[0].inference, "This may indicate missing material.")
        self.assertEqual(evidence_items[0].uncertainty, "The contrast may come from preparation.")
        self.assertEqual(evidence_items[0].confidence, "medium")
        self.assertEqual(evidence_items[0].coordinates[0]["center_x_percent"], 25)


class FaStemBriefWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_brief_attaches_photo_bundles_and_records_batch_evidence(self) -> None:
        conversation = RecordingFaStemConversation(
            [
                """```json
{
  "candidate_observations": [
    {
      "tile_label": "A2",
      "observation": "Dark void-like contrast appears near the via edge.",
      "inference": "This may indicate missing material near the electrical path.",
      "uncertainty": "The contrast could also come from sample preparation.",
      "confidence": "medium",
      "coordinates": [{"center_x_percent": 25, "center_y_percent": 40, "radius_percent": 12}]
    }
  ]
}
```""",
                """```json
{"candidate_observations": []}
```""",
            ]
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            case_folder = workspace / "case-a"
            case_folder.mkdir()
            for index in range(10):
                image = Image.new("RGB", (32, 24), color=(index * 20, 20, 120))
                image.save(case_folder / f"stem-{index:02d}.jpg")

            result = await run_fa_stem_brief(
                workspace=workspace,
                case_folder=case_folder,
                case_background="Leakage fails at VDD after stress.",
                conversation=conversation,
            )

            self.assertTrue(result.report_path.exists())

        self.assertEqual(len(conversation.attached_files), 2)
        self.assertTrue(all(path.name.endswith(".png") for path in conversation.attached_files))
        self.assertEqual(len(conversation.prompts), 2)
        self.assertIn("Batch 1 of 2", conversation.prompts[0])
        self.assertIn("Batch 2 of 2", conversation.prompts[1])
        self.assertIn("A2: case-a/stem-01.jpg", conversation.prompts[0])

        self.assertEqual(len(result.bundles), 2)
        self.assertEqual(len(result.covered_source_ids), 10)
        self.assertEqual(result.covered_source_ids[0], "case-a/stem-00.jpg")
        self.assertEqual(result.covered_source_ids[-1], "case-a/stem-09.jpg")
        self.assertEqual(len(result.batch_results), 2)
        self.assertEqual(result.batch_results[0].covered_source_ids[0], "case-a/stem-00.jpg")
        self.assertEqual(result.batch_results[0].covered_source_ids[-1], "case-a/stem-08.jpg")
        self.assertEqual(result.batch_results[1].covered_source_ids, ("case-a/stem-09.jpg",))
        self.assertEqual(len(result.batch_results[0].evidence_items), 1)
        self.assertEqual(result.batch_results[1].evidence_items, ())
        self.assertEqual(len(result.evidence_items), 1)
        self.assertEqual(result.evidence.source_id, "case-a/stem-01.jpg")
        self.assertEqual(
            result.evidence.observation,
            "Dark void-like contrast appears near the via edge.",
        )
        self.assertEqual(
            result.evidence.inference,
            "This may indicate missing material near the electrical path.",
        )
        self.assertEqual(
            result.evidence.uncertainty,
            "The contrast could also come from sample preparation.",
        )
        self.assertEqual(result.evidence.confidence, "medium")
        self.assertEqual(result.evidence.coordinates[0]["center_x_percent"], 25.0)


if __name__ == "__main__":
    unittest.main()
