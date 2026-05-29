from __future__ import annotations

import json
from pathlib import Path

from atlas.attachment_evidence import AttachmentEvidence, format_saved_attachment_evidence
from atlas.fa_stem_bundles import PhotoBundle
from atlas.fa_stem_models import FaStemCandidateReviewResult
from atlas.workspace_paths import workspace_relative_path


def build_photo_bundle_prompt(
    *,
    case_background: str,
    bundle: PhotoBundle,
    batch_number: int,
    total_batches: int,
) -> str:
    mapping = "\n".join(f"- {tile.label}: {tile.source_id}" for tile in bundle.tiles)
    return f"""You are acting as a senior semiconductor process failure analysis engineer.

Atlas has attached one 3x3 STEM Photo Bundle for this turn.

Batch {batch_number} of {total_batches}

Tile-to-source mapping:
{mapping}

Case background:
{case_background.strip()}

Inspect this bundle for first-pass triage only. Return candidate observations, not final conclusions.
Do not choose a full-case primary suspect yet.

Return exactly one fenced JSON block with this shape:

```json
{{
  "candidate_observations": [
    {{
      "tile_label": "A1",
      "observation": "short description of what is visible",
      "inference": "short explanation of what the observation may mean",
      "uncertainty": "short note about what is unclear or could be another cause",
      "confidence": "low | medium | high",
      "coordinates": [
        {{"center_x_percent": 50, "center_y_percent": 50, "radius_percent": 10}}
      ]
    }}
  ]
}}
```

Use tile labels from the mapping. Coordinates are optional and should be relative to the source tile image."""


def build_candidate_review_prompt(
    *,
    case_background: str,
    source_id: str,
    first_pass_evidence: tuple[AttachmentEvidence, ...],
) -> str:
    evidence_text = format_saved_attachment_evidence(first_pass_evidence)
    return f"""You are acting as a senior semiconductor process failure analysis engineer.

Atlas has attached the original STEM source image for this turn.

Candidate source image: {source_id}

Case background:
{case_background.strip()}

First-pass saved text evidence for this candidate:
{evidence_text}

Review the attached original image at higher detail. Return exactly one fenced JSON block with this shape:

```json
{{
  "candidate_review": {{
    "observation": "short description of what is visible in the original image",
    "reason": "why this finding matters for the case",
    "uncertainty": "what is unclear or could be another cause",
    "confidence": "low | medium | high",
    "classification": "primary-suspect-relevant | profile-only",
    "coordinates": [
      {{"center_x_percent": 50, "center_y_percent": 50, "radius_percent": 10}}
    ]
  }}
}}
```

Use percent coordinates relative to the attached original image. Separate direct observation from reasoning."""


def build_final_ranking_prompt(
    *,
    case_background: str,
    first_pass_evidence: tuple[AttachmentEvidence, ...],
    candidate_review_results: tuple[FaStemCandidateReviewResult, ...],
) -> str:
    first_pass_text = format_saved_attachment_evidence(first_pass_evidence)
    candidate_review_text = format_candidate_review_evidence(candidate_review_results)
    return f"""You are acting as a senior semiconductor process failure analysis engineer.

Choose the full-case final FA STEM triage ranking from saved text evidence only.
Do not assume prior attachments are still visible.

Case background:
{case_background.strip()}

Saved first-pass bundle evidence:
{first_pass_text}

Saved second-pass original-image review evidence:
{candidate_review_text}

Return exactly one fenced JSON block with this shape:

```json
{{
  "primary_suspect": {{
    "status": "selected | unclear",
    "source_id": "case-a/stem-01.jpg",
    "reason": "why this is the primary suspect, or why primary suspect is unclear",
    "uncertainty": "what still needs human FA review",
    "confidence": "low | medium | high",
    "coordinates": [
      {{"center_x_percent": 50, "center_y_percent": 50, "radius_percent": 10}}
    ]
  }},
  "profile_anomalies": [
    {{
      "source_id": "case-a/stem-02.jpg",
      "reason": "why this is profile-only",
      "uncertainty": "what remains unclear",
      "confidence": "low | medium | high",
      "coordinates": []
    }}
  ]
}}
```

Use status "selected" for exactly one primary electrical suspect when evidence supports it.
Use status "unclear" and source_id null when evidence is insufficient.
Profile anomalies can include zero or more findings."""


def format_candidate_review_evidence(candidate_review_results: tuple[FaStemCandidateReviewResult, ...]) -> str:
    if not candidate_review_results:
        return "Saved second-pass review evidence:\nNone."

    sections = ["Saved second-pass review evidence:"]
    for index, review in enumerate(candidate_review_results, start=1):
        coordinates_json = (
            json.dumps(list(review.coordinates), ensure_ascii=False, sort_keys=True)
            if review.coordinates
            else "none"
        )
        sections.append(
            "\n".join(
                [
                    f"Candidate review {index}:",
                    f"Source: {review.source_id}",
                    f"Classification: {review.classification}",
                    f"Observation: {review.observation}",
                    f"Reason: {review.reason}",
                    f"Uncertainty: {review.uncertainty}",
                    f"Confidence: {review.confidence}",
                    f"Coordinates: {coordinates_json}",
                ]
            )
        )
    return "\n\n".join(sections)


def build_single_image_prompt(
    *,
    workspace: Path,
    case_folder: Path,
    image_path: Path,
    case_background: str,
) -> str:
    image_reference = workspace_relative_path(workspace, image_path)
    folder_reference = workspace_relative_path(workspace, case_folder)
    return f"""You are acting as a senior semiconductor process failure analysis engineer.

Atlas has attached one STEM image for this turn.

Case folder: {folder_reference}
Selected image: {image_reference}

Case background:
{case_background.strip()}

Inspect the attached STEM image and suggest one AI triage circle for the most relevant suspicious location.

Return exactly one fenced JSON block with this shape:

```json
{{
  "center_x_percent": 50,
  "center_y_percent": 50,
  "radius_percent": 10,
  "observation": "short description of what is visible in the image",
  "inference": "short explanation of what the observation may mean",
  "uncertainty": "short note about what is unclear or could be another cause",
  "confidence": "low | medium | high"
}}
```

Use percent coordinates relative to the image: x from left to right, y from top to bottom.
Separate direct visual observations from inference. Preserve uncertainty even when confidence is high.
Do not claim this is a final FA root cause. This is only an AI-suggested triage marker."""
