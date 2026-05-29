from __future__ import annotations

import unittest

from atlas.attachment_evidence import AttachmentEvidence, format_saved_attachment_evidence


class AttachmentEvidenceTests(unittest.TestCase):
    def test_evidence_round_trips_and_renders_as_saved_text_context(self) -> None:
        evidence = AttachmentEvidence(
            source_id="case-a/a-first.jpg",
            observation="Dark void-like contrast appears near the via edge.",
            inference="This may indicate missing material near the electrical path.",
            uncertainty="The contrast could also come from sample preparation.",
            confidence="medium",
            coordinates=(
                {
                    "center_x_percent": 25,
                    "center_y_percent": 40,
                    "radius_percent": 12,
                },
            ),
        )

        restored = AttachmentEvidence.from_dict(evidence.to_dict())
        saved_context = format_saved_attachment_evidence([restored])

        self.assertEqual(restored.source_id, "case-a/a-first.jpg")
        self.assertEqual(restored.observation, "Dark void-like contrast appears near the via edge.")
        self.assertEqual(
            restored.inference,
            "This may indicate missing material near the electrical path.",
        )
        self.assertEqual(restored.uncertainty, "The contrast could also come from sample preparation.")
        self.assertEqual(restored.confidence, "medium")
        self.assertEqual(restored.coordinates[0]["center_x_percent"], 25)

        self.assertIn("Saved attachment evidence", saved_context)
        self.assertIn("Do not assume prior attachments are still visible", saved_context)
        self.assertIn("Source: case-a/a-first.jpg", saved_context)
        self.assertIn("Observation: Dark void-like contrast appears near the via edge.", saved_context)
        self.assertIn("Inference: This may indicate missing material near the electrical path.", saved_context)
        self.assertIn("Uncertainty: The contrast could also come from sample preparation.", saved_context)
        self.assertIn("Confidence: medium", saved_context)
        self.assertIn('"center_x_percent": 25', saved_context)


if __name__ == "__main__":
    unittest.main()
