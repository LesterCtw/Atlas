from __future__ import annotations

import json
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


def fenced_json(payload: dict[str, object]) -> str:
    return "```json\n" + json.dumps(payload) + "\n```"


def photo_bundle_response(tile_labels: tuple[str, ...]) -> str:
    return fenced_json(
        {
            "candidate_observations": [
                {
                    "tile_label": tile_label,
                    "observation": f"Candidate contrast at {tile_label}.",
                    "inference": "May be relevant to the electrical path.",
                    "uncertainty": "Could be preparation contrast.",
                    "confidence": "medium",
                }
                for tile_label in tile_labels
            ]
        }
    )


def candidate_review_response(index: int, classification: str = "profile-only") -> str:
    return fenced_json(
        {
            "candidate_review": {
                "observation": f"Original image review observation {index}.",
                "reason": f"Review reason {index}.",
                "uncertainty": "Needs human FA confirmation.",
                "confidence": "medium",
                "classification": classification,
                "coordinates": [],
            }
        }
    )


def unclear_final_ranking_response() -> str:
    return fenced_json(
        {
            "primary_suspect": {
                "status": "unclear",
                "source_id": None,
                "reason": "Saved evidence is not strong enough to choose one primary suspect.",
                "uncertainty": "More FA review is required.",
                "confidence": "low",
                "coordinates": [],
            },
            "profile_anomalies": [],
        }
    )


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

    def test_parse_plain_json_circle_response_after_markdown_rendering_removed_fence(self) -> None:
        circle = parse_fa_stem_circle(
            """The suggested mark is:

JSON
{
  "center_x_percent": 25,
  "center_y_percent": 40,
  "radius_percent": 12,
  "reason": "Void-like contrast near the via edge.",
  "confidence": "medium"
}
"""
        )

        self.assertEqual(circle.center_x_percent, 25.0)
        self.assertEqual(circle.center_y_percent, 40.0)
        self.assertEqual(circle.radius_percent, 12.0)

    def test_parse_rejects_malformed_or_incomplete_json(self) -> None:
        cases = {
            "missing-json": ("No JSON here.", "JSON"),
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
    async def test_brief_writes_demo_report_package_with_original_image_overlays(self) -> None:
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
    },
    {
      "tile_label": "A3",
      "observation": "Profile roughness appears near the upper edge.",
      "inference": "This may be a profile anomaly rather than the electrical root cause.",
      "uncertainty": "The roughness may be normal process variation.",
      "confidence": "low",
      "coordinates": [{"center_x_percent": 55, "center_y_percent": 35, "radius_percent": 8}]
    }
  ]
}
```""",
                """```json
{
  "candidate_review": {
    "observation": "The original image confirms a dark gap at the via edge.",
    "reason": "The feature overlaps the expected current path.",
    "uncertainty": "Local contrast may still be preparation-related.",
    "confidence": "high",
    "classification": "primary-suspect-relevant",
    "coordinates": [{"center_x_percent": 28, "center_y_percent": 42, "radius_percent": 9}]
  }
}
```""",
                """```json
{
  "candidate_review": {
    "observation": "The original image confirms profile roughness.",
    "reason": "The feature is visible but does not align with the likely current path.",
    "uncertainty": "Could be normal process variation.",
    "confidence": "medium",
    "classification": "profile-only",
    "coordinates": [{"center_x_percent": 58, "center_y_percent": 36, "radius_percent": 7}]
  }
}
```""",
                """```json
{
  "primary_suspect": {
    "status": "selected",
    "source_id": "case-a/stem-01.jpg",
    "reason": "The confirmed via-edge gap best matches the leakage background.",
    "uncertainty": "Electrical correlation still needs human FA review.",
    "confidence": "high",
    "coordinates": [{"center_x_percent": 28, "center_y_percent": 42, "radius_percent": 9}]
  },
  "profile_anomalies": [
    {
      "source_id": "case-a/stem-02.jpg",
      "reason": "Profile roughness is visible but not clearly electrical.",
      "uncertainty": "Could be normal process variation.",
      "confidence": "medium",
      "coordinates": [{"center_x_percent": 58, "center_y_percent": 36, "radius_percent": 7}]
    }
  ]
}
```""",
            ]
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            case_folder = workspace / "case-a"
            case_folder.mkdir()
            for index in range(3):
                image = Image.new("RGB", (32, 24), color=(index * 50, 20, 120))
                image.save(case_folder / f"stem-{index:02d}.jpg")
            original_bytes = {
                image_path.name: image_path.read_bytes()
                for image_path in sorted(case_folder.glob("*.jpg"))
            }

            result = await run_fa_stem_brief(
                workspace=workspace,
                case_folder=case_folder,
                case_background="Leakage fails at VDD after stress.",
                conversation=conversation,
            )

            artifact_dir = case_folder / "atlas-fa-stem-report"
            report_html = result.report_path.read_text(encoding="utf-8")

            self.assertEqual(result.artifact_dir, artifact_dir)
            self.assertTrue((artifact_dir / "bundles" / "photo-bundle-001.png").exists())
            self.assertTrue((artifact_dir / "metadata.json").exists())
            self.assertTrue((artifact_dir / "model-outputs.json").exists())
            self.assertEqual(
                original_bytes,
                {
                    image_path.name: image_path.read_bytes()
                    for image_path in sorted(case_folder.glob("*.jpg"))
                },
            )

        self.assertIn("<title>FA STEM Suspect Triage Report</title>", report_html)
        self.assertIn("AI-suggested triage markers", report_html)
        self.assertIn("not measurement-grade annotations", report_html)
        self.assertIn("not final FA conclusions", report_html)
        self.assertIn("Case Background", report_html)
        self.assertIn("Scan Summary", report_html)
        self.assertIn("Batch Coverage", report_html)
        self.assertIn("Candidate Review Summary", report_html)
        self.assertIn("Primary Electrical Suspect", report_html)
        self.assertIn("Profile Anomalies", report_html)
        self.assertIn("Not-Flagged Images", report_html)
        self.assertIn("Recommended Next Actions", report_html)
        self.assertIn('src="stem-01.jpg"', report_html)
        self.assertIn('src="stem-02.jpg"', report_html)
        self.assertIn("overlay-circle primary-suspect", report_html)
        self.assertIn("overlay-circle profile-anomaly", report_html)
        self.assertIn("left: 28.0%;", report_html)
        self.assertIn("top: 42.0%;", report_html)
        self.assertIn("width: 18.0%;", report_html)
        self.assertIn("left: 58.0%;", report_html)
        self.assertIn("top: 36.0%;", report_html)
        self.assertIn("width: 14.0%;", report_html)
        self.assertIn("stem-00.jpg", report_html)

    async def test_brief_reattaches_candidate_original_image_and_records_final_primary_suspect(self) -> None:
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
{
  "candidate_review": {
    "observation": "The original image confirms a dark gap at the via edge.",
    "reason": "The feature overlaps the expected current path.",
    "uncertainty": "Local contrast may still be preparation-related.",
    "confidence": "high",
    "classification": "primary-suspect-relevant",
    "coordinates": [{"center_x_percent": 28, "center_y_percent": 42, "radius_percent": 9}]
  }
}
```""",
                """```json
{
  "primary_suspect": {
    "status": "selected",
    "source_id": "case-a/stem-01.jpg",
    "reason": "The confirmed via-edge gap best matches the leakage background.",
    "uncertainty": "Electrical correlation still needs human FA review.",
    "confidence": "high",
    "coordinates": [{"center_x_percent": 28, "center_y_percent": 42, "radius_percent": 9}]
  },
  "profile_anomalies": [
    {
      "source_id": "case-a/stem-02.jpg",
      "reason": "Profile roughness is visible but not clearly electrical.",
      "uncertainty": "Could be normal process variation.",
      "confidence": "medium",
      "coordinates": []
    }
  ]
}
```""",
            ]
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            case_folder = workspace / "case-a"
            case_folder.mkdir()
            for index in range(3):
                image = Image.new("RGB", (32, 24), color=(index * 50, 20, 120))
                image.save(case_folder / f"stem-{index:02d}.jpg")

            result = await run_fa_stem_brief(
                workspace=workspace,
                case_folder=case_folder,
                case_background="Leakage fails at VDD after stress.",
                conversation=conversation,
            )

        self.assertEqual(len(conversation.attached_files), 2)
        self.assertEqual(conversation.attached_files[0].suffix, ".png")
        self.assertEqual(conversation.attached_files[1].name, "stem-01.jpg")
        self.assertEqual(len(conversation.prompts), 3)
        self.assertIn("Candidate source image: case-a/stem-01.jpg", conversation.prompts[1])
        self.assertIn("primary-suspect-relevant", conversation.prompts[1])
        self.assertIn("profile-only", conversation.prompts[1])
        self.assertIn("Do not assume prior attachments are still visible", conversation.prompts[2])
        self.assertIn("Dark void-like contrast appears near the via edge.", conversation.prompts[2])
        self.assertIn("The original image confirms a dark gap at the via edge.", conversation.prompts[2])

        self.assertEqual(result.candidate_source_ids, ("case-a/stem-01.jpg",))
        self.assertEqual(len(result.candidate_review_results), 1)
        self.assertEqual(result.candidate_review_results[0].source_id, "case-a/stem-01.jpg")
        self.assertEqual(result.candidate_review_results[0].classification, "primary-suspect-relevant")
        self.assertEqual(result.final_ranking.primary_suspect.source_id, "case-a/stem-01.jpg")
        self.assertEqual(result.final_ranking.primary_suspect.status, "selected")
        self.assertEqual(len(result.final_ranking.profile_anomalies), 1)

    async def test_brief_reviews_no_more_than_ten_candidate_original_images(self) -> None:
        conversation = RecordingFaStemConversation(
            [
                photo_bundle_response(("A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3")),
                photo_bundle_response(("A1", "A2", "A3")),
                *[candidate_review_response(index) for index in range(10)],
                unclear_final_ranking_response(),
            ]
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            case_folder = workspace / "case-a"
            case_folder.mkdir()
            for index in range(12):
                image = Image.new("RGB", (32, 24), color=(index * 20, 20, 120))
                image.save(case_folder / f"stem-{index:02d}.jpg")

            result = await run_fa_stem_brief(
                workspace=workspace,
                case_folder=case_folder,
                case_background="Leakage fails at VDD after stress.",
                conversation=conversation,
            )

        self.assertEqual(len(result.candidate_source_ids), 10)
        self.assertEqual(result.candidate_source_ids[0], "case-a/stem-00.jpg")
        self.assertEqual(result.candidate_source_ids[-1], "case-a/stem-09.jpg")
        self.assertEqual(
            [path.name for path in conversation.attached_files[2:]],
            [f"stem-{index:02d}.jpg" for index in range(10)],
        )
        self.assertEqual(len(conversation.prompts), 13)

    async def test_brief_allows_unclear_primary_while_preserving_profile_anomalies(self) -> None:
        conversation = RecordingFaStemConversation(
            [
                photo_bundle_response(("A1",)),
                candidate_review_response(0, classification="profile-only"),
                fenced_json(
                    {
                        "primary_suspect": {
                            "status": "unclear",
                            "source_id": None,
                            "reason": "Evidence is only morphological and does not identify one electrical suspect.",
                            "uncertainty": "Electrical correlation is missing.",
                            "confidence": "low",
                            "coordinates": [],
                        },
                        "profile_anomalies": [
                            {
                                "source_id": "case-a/stem-00.jpg",
                                "reason": "Profile roughness is visible but not clearly electrical.",
                                "uncertainty": "Could be normal process variation.",
                                "confidence": "medium",
                                "coordinates": [],
                            }
                        ],
                    }
                ),
            ]
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            case_folder = workspace / "case-a"
            case_folder.mkdir()
            Image.new("RGB", (32, 24), color=(180, 20, 20)).save(case_folder / "stem-00.jpg")

            result = await run_fa_stem_brief(
                workspace=workspace,
                case_folder=case_folder,
                case_background="Leakage fails at VDD after stress.",
                conversation=conversation,
            )
            report_html = result.report_path.read_text(encoding="utf-8")

        self.assertEqual(result.final_ranking.primary_suspect.status, "unclear")
        self.assertIsNone(result.final_ranking.primary_suspect.source_id)
        self.assertEqual(len(result.final_ranking.profile_anomalies), 1)
        self.assertEqual(result.final_ranking.profile_anomalies[0].source_id, "case-a/stem-00.jpg")
        self.assertIn("primary suspect unclear", report_html)
        self.assertIn("Profile Anomalies", report_html)
        self.assertIn("case-a/stem-00.jpg", report_html)
        self.assertNotIn("overlay-circle primary-suspect", report_html)

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
                candidate_review_response(0, classification="primary-suspect-relevant"),
                fenced_json(
                    {
                        "primary_suspect": {
                            "status": "selected",
                            "source_id": "case-a/stem-01.jpg",
                            "reason": "The reviewed candidate is the best electrical suspect.",
                            "uncertainty": "Human FA review is still required.",
                            "confidence": "medium",
                            "coordinates": [],
                        },
                        "profile_anomalies": [],
                    }
                ),
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

        self.assertEqual(len(conversation.attached_files), 3)
        self.assertTrue(all(path.name.endswith(".png") for path in conversation.attached_files[:2]))
        self.assertEqual(conversation.attached_files[2].name, "stem-01.jpg")
        self.assertEqual(len(conversation.prompts), 4)
        self.assertIn("Batch 1 of 2", conversation.prompts[0])
        self.assertIn("Batch 2 of 2", conversation.prompts[1])
        self.assertIn("A2: case-a/stem-01.jpg", conversation.prompts[0])
        self.assertIn("Candidate source image: case-a/stem-01.jpg", conversation.prompts[2])
        self.assertIn("Saved second-pass original-image review evidence", conversation.prompts[3])

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
        self.assertEqual(result.final_ranking.primary_suspect.source_id, "case-a/stem-01.jpg")


if __name__ == "__main__":
    unittest.main()
