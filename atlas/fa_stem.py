from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Protocol

from atlas.attachment_evidence import AttachmentEvidence, format_saved_attachment_evidence
from atlas.fa_stem_bundles import (
    REPORT_ARTIFACT_DIR_NAME,
    PhotoBundle,
    PhotoBundleTile,
    collect_stem_images,
    create_photo_bundles,
    report_artifact_dir,
)
from atlas.fa_stem_models import (
    FaStemBriefError,
    FaStemBriefResult,
    FaStemCandidateReviewResult,
    FaStemCircle,
    FaStemFinalFinding,
    FaStemFinalRanking,
    PhotoBundleBatchResult,
)
from atlas.json_fences import (
    JsonFencePayloadError,
    MalformedJsonFenceError,
    MissingJsonFenceError,
    parse_first_json_fence_object,
)
from atlas.workspace_paths import resolve_workspace_path, workspace_relative_path


_REPORT_ASSET_DIR_NAME = "assets"
_MAX_CANDIDATE_REVIEWS = 10
REPORT_FILE_NAME = "atlas-fa-stem-brief.html"


class FaStemConversation(Protocol):
    async def send_single_turn(self, user_prompt: str) -> str:
        pass

    async def attach_file(self, path: Path) -> None:
        pass


async def run_fa_stem_brief(
    *,
    workspace: Path,
    case_folder: Path,
    case_background: str,
    conversation: FaStemConversation,
) -> FaStemBriefResult:
    if not case_background.strip():
        raise FaStemBriefError("Case background is required.")

    status_events = ["selecting-fa-stem-image"]
    images = collect_stem_images(case_folder)
    if not images:
        raise FaStemBriefError("No .jpg or .jpeg image found in the selected folder.")
    bundles = create_photo_bundles(
        workspace=workspace,
        case_folder=case_folder,
        images=images,
    )
    evidence_items: list[AttachmentEvidence] = []
    batch_results: list[PhotoBundleBatchResult] = []
    first_pass_model_outputs: list[str] = []
    try:
        for index, bundle in enumerate(bundles, start=1):
            status_events.append("uploading-attachment")
            await conversation.attach_file(bundle.path)
            status_events.append("attachment-uploaded")
            status_events.append("waiting-for-model")
            model_response = await conversation.send_single_turn(
                build_photo_bundle_prompt(
                    case_background=case_background,
                    bundle=bundle,
                    batch_number=index,
                    total_batches=len(bundles),
                )
            )
            first_pass_model_outputs.append(model_response)
            status_events.append("parsing-fa-stem-response")
            batch_evidence_items = parse_photo_bundle_candidate_evidence(
                model_response,
                bundle=bundle,
            )
            evidence_items.extend(batch_evidence_items)
            batch_results.append(
                PhotoBundleBatchResult(
                    bundle=bundle,
                    covered_source_ids=tuple(tile.source_id for tile in bundle.tiles),
                    evidence_items=batch_evidence_items,
                )
            )
    except Exception as error:
        raise FaStemBriefError(f"FA STEM brief failed while talking to tGenie: {error}") from error

    covered_source_ids = tuple(workspace_relative_path(workspace, image) for image in images)
    source_paths_by_id = dict(zip(covered_source_ids, images, strict=True))
    candidate_source_ids = select_candidate_source_ids(tuple(evidence_items))
    candidate_review_results: list[FaStemCandidateReviewResult] = []
    candidate_review_model_outputs: list[str] = []
    try:
        for source_id in candidate_source_ids:
            source_path = source_paths_by_id[source_id]
            first_pass_evidence = tuple(evidence for evidence in evidence_items if evidence.source_id == source_id)
            status_events.append("uploading-attachment")
            await conversation.attach_file(source_path)
            status_events.append("attachment-uploaded")
            status_events.append("waiting-for-model")
            model_response = await conversation.send_single_turn(
                build_candidate_review_prompt(
                    case_background=case_background,
                    source_id=source_id,
                    first_pass_evidence=first_pass_evidence,
                )
            )
            candidate_review_model_outputs.append(model_response)
            status_events.append("parsing-fa-stem-response")
            candidate_review_results.append(
                parse_candidate_review_result(
                    model_response,
                    source_id=source_id,
                )
            )

        status_events.append("waiting-for-model")
        final_response = await conversation.send_single_turn(
            build_final_ranking_prompt(
                case_background=case_background,
                first_pass_evidence=tuple(evidence_items),
                candidate_review_results=tuple(candidate_review_results),
            )
        )
        status_events.append("parsing-fa-stem-response")
        final_ranking = parse_final_ranking(final_response)
    except Exception as error:
        raise FaStemBriefError(f"FA STEM brief failed while talking to tGenie: {error}") from error

    status_events.append("writing-fa-stem-report")
    report_path = write_photo_bundle_report(
        workspace=workspace,
        case_folder=case_folder,
        case_background=case_background,
        bundles=bundles,
        batch_results=tuple(batch_results),
        covered_source_ids=covered_source_ids,
        evidence_items=tuple(evidence_items),
        candidate_source_ids=candidate_source_ids,
        candidate_review_results=tuple(candidate_review_results),
        final_ranking=final_ranking,
        first_pass_model_outputs=tuple(first_pass_model_outputs),
        candidate_review_model_outputs=tuple(candidate_review_model_outputs),
        final_ranking_model_output=final_response,
    )
    return FaStemBriefResult(
        report_path=report_path,
        artifact_dir=report_artifact_dir(case_folder),
        selected_image=images[0],
        bundles=bundles,
        batch_results=tuple(batch_results),
        covered_source_ids=covered_source_ids,
        evidence_items=tuple(evidence_items),
        candidate_source_ids=candidate_source_ids,
        candidate_review_results=tuple(candidate_review_results),
        final_ranking=final_ranking,
        status_events=status_events,
    )


def select_single_stem_image(case_folder: Path) -> Path:
    images = collect_stem_images(case_folder)
    if not images:
        raise FaStemBriefError("No .jpg or .jpeg image found in the selected folder.")
    return images[0].resolve()


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


def parse_photo_bundle_candidate_evidence(
    model_response: str,
    *,
    bundle: PhotoBundle,
) -> tuple[AttachmentEvidence, ...]:
    payload = _parse_fenced_json_object(model_response)
    candidates = payload.get("candidate_observations")
    if not isinstance(candidates, list):
        raise FaStemBriefError("tGenie JSON response is missing candidate_observations.")

    tiles_by_label = {tile.label: tile for tile in bundle.tiles}
    evidence_items: list[AttachmentEvidence] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise FaStemBriefError("Each candidate observation must be an object.")
        tile_label = str(candidate.get("tile_label") or "")
        tile = tiles_by_label.get(tile_label)
        if tile is None:
            raise FaStemBriefError(f"Unknown tile_label in candidate observation: {tile_label}")
        evidence_items.append(
            AttachmentEvidence(
                source_id=tile.source_id,
                observation=str(candidate.get("observation") or ""),
                inference=str(candidate.get("inference") or ""),
                uncertainty=str(candidate.get("uncertainty") or ""),
                confidence=str(candidate.get("confidence") or ""),
                coordinates=_candidate_coordinates(candidate.get("coordinates")),
            )
        )
    return tuple(evidence_items)


def select_candidate_source_ids(evidence_items: tuple[AttachmentEvidence, ...]) -> tuple[str, ...]:
    selected: list[str] = []
    for evidence in evidence_items:
        if evidence.source_id not in selected:
            selected.append(evidence.source_id)
        if len(selected) == _MAX_CANDIDATE_REVIEWS:
            break
    return tuple(selected)


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


def parse_candidate_review_result(
    model_response: str,
    *,
    source_id: str,
) -> FaStemCandidateReviewResult:
    payload = _parse_fenced_json_object(model_response)
    review = payload.get("candidate_review")
    if not isinstance(review, dict):
        raise FaStemBriefError("tGenie JSON response is missing candidate_review.")

    missing_fields = [
        field
        for field in (
            "observation",
            "reason",
            "uncertainty",
            "confidence",
            "classification",
        )
        if not str(review.get(field) or "").strip()
    ]
    if missing_fields:
        raise FaStemBriefError("candidate_review is missing: " + ", ".join(missing_fields))

    classification = str(review["classification"])
    if classification not in {"primary-suspect-relevant", "profile-only"}:
        raise FaStemBriefError("candidate_review classification must be primary-suspect-relevant or profile-only.")

    return FaStemCandidateReviewResult(
        source_id=source_id,
        observation=str(review["observation"]),
        reason=str(review["reason"]),
        uncertainty=str(review["uncertainty"]),
        confidence=str(review["confidence"]),
        classification=classification,
        coordinates=_candidate_coordinates(review.get("coordinates")),
    )


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


def parse_final_ranking(model_response: str) -> FaStemFinalRanking:
    payload = _parse_fenced_json_object(model_response)
    primary_payload = payload.get("primary_suspect")
    if not isinstance(primary_payload, dict):
        raise FaStemBriefError("tGenie JSON response is missing primary_suspect.")
    anomalies_payload = payload.get("profile_anomalies")
    if not isinstance(anomalies_payload, list):
        raise FaStemBriefError("tGenie JSON response is missing profile_anomalies.")

    primary_suspect = _parse_final_finding(primary_payload, require_source=False)
    if primary_suspect.status not in {"selected", "unclear"}:
        raise FaStemBriefError("primary_suspect status must be selected or unclear.")
    if primary_suspect.status == "selected" and not primary_suspect.source_id:
        raise FaStemBriefError("selected primary_suspect requires source_id.")
    if primary_suspect.status == "unclear" and primary_suspect.source_id:
        raise FaStemBriefError("unclear primary_suspect must not include source_id.")

    profile_anomalies = tuple(
        _parse_final_finding(anomaly, require_source=True, default_status="profile-only")
        for anomaly in anomalies_payload
    )
    return FaStemFinalRanking(
        primary_suspect=primary_suspect,
        profile_anomalies=profile_anomalies,
    )


def _parse_final_finding(
    payload: object,
    *,
    require_source: bool,
    default_status: str | None = None,
) -> FaStemFinalFinding:
    if not isinstance(payload, dict):
        raise FaStemBriefError("final ranking findings must be objects.")
    status = str(payload.get("status") or default_status or "")
    source_value = payload.get("source_id")
    source_id = str(source_value) if source_value is not None else None
    missing_fields = [
        field
        for field in (
            "reason",
            "uncertainty",
            "confidence",
        )
        if not str(payload.get(field) or "").strip()
    ]
    if not status:
        missing_fields.append("status")
    if require_source and not source_id:
        missing_fields.append("source_id")
    if missing_fields:
        raise FaStemBriefError("final ranking finding is missing: " + ", ".join(missing_fields))
    return FaStemFinalFinding(
        status=status,
        source_id=source_id,
        reason=str(payload["reason"]),
        uncertainty=str(payload["uncertainty"]),
        confidence=str(payload["confidence"]),
        coordinates=_candidate_coordinates(payload.get("coordinates")),
    )


def _parse_fenced_json_object(model_response: str) -> dict[str, object]:
    try:
        return parse_first_json_fence_object(model_response)
    except MissingJsonFenceError as error:
        raise FaStemBriefError("tGenie response did not include a fenced JSON block.") from error
    except MalformedJsonFenceError as error:
        raise FaStemBriefError("tGenie response included malformed JSON.") from error
    except JsonFencePayloadError as error:
        raise FaStemBriefError("tGenie JSON response must be an object.") from error


def _candidate_coordinates(value: object) -> tuple[dict[str, object], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise FaStemBriefError("candidate coordinates must be a list of objects.")
    if not all(isinstance(coordinate, dict) for coordinate in value):
        raise FaStemBriefError("candidate coordinates must be a list of objects.")
    return tuple(dict(coordinate) for coordinate in value)


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


def parse_fa_stem_circle(model_response: str) -> FaStemCircle:
    payload = _parse_fenced_json_object(model_response)
    missing_fields = [
        field
        for field in (
            "center_x_percent",
            "center_y_percent",
            "radius_percent",
            "confidence",
        )
        if field not in payload
    ]
    observation = str(payload.get("observation") or payload.get("reason") or "")
    inference = str(payload.get("inference") or payload.get("reason") or "")
    uncertainty = str(payload.get("uncertainty") or "Uncertainty not provided by model.")
    if not observation:
        missing_fields.append("observation")
    if not inference:
        missing_fields.append("inference")
    if missing_fields:
        raise FaStemBriefError("tGenie JSON response is missing: " + ", ".join(missing_fields))

    try:
        return FaStemCircle(
            center_x_percent=float(payload["center_x_percent"]),
            center_y_percent=float(payload["center_y_percent"]),
            radius_percent=float(payload["radius_percent"]),
            observation=observation,
            inference=inference,
            uncertainty=uncertainty,
            confidence=str(payload["confidence"]),
        )
    except (TypeError, ValueError) as error:
        raise FaStemBriefError("tGenie JSON coordinates must be numeric percent values.") from error


def build_fa_stem_evidence(*, source_id: str, circle: FaStemCircle) -> AttachmentEvidence:
    return AttachmentEvidence(
        source_id=source_id,
        observation=circle.observation,
        inference=circle.inference,
        uncertainty=circle.uncertainty,
        confidence=circle.confidence,
        coordinates=(
            {
                "center_x_percent": circle.center_x_percent,
                "center_y_percent": circle.center_y_percent,
                "radius_percent": circle.radius_percent,
            },
        ),
    )


def write_single_image_report(
    *,
    case_folder: Path,
    image_path: Path,
    case_background: str,
    circle: FaStemCircle,
) -> Path:
    image_reference = image_path.relative_to(case_folder.resolve()).as_posix()
    diameter = circle.radius_percent * 2
    report_path = case_folder / REPORT_FILE_NAME
    report_path.write_text(
        f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>FA STEM Brief Report</title>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      font-family: Arial, sans-serif;
      color: #151515;
      background: #f5f5f5;
    }}
    main {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    .image-wrap {{
      position: relative;
      display: inline-block;
      max-width: 100%;
      background: #111;
    }}
    img {{
      display: block;
      max-width: 100%;
      height: auto;
    }}
    .circle {{
      position: absolute;
      left: {circle.center_x_percent:.1f}%;
      top: {circle.center_y_percent:.1f}%;
      width: {diameter:.1f}%;
      aspect-ratio: 1;
      border: 3px solid #d31f1f;
      border-radius: 50%;
      transform: translate(-50%, -50%);
      box-sizing: border-box;
      pointer-events: none;
    }}
    .note {{
      color: #555;
    }}
  </style>
</head>
<body>
  <main>
    <h1>FA STEM Brief Report</h1>
    <p class="note">This report is an AI-suggested triage marker, not a measurement-grade annotation or final FA conclusion.</p>
    <h2>Case Background</h2>
    <p>{html.escape(case_background)}</p>
    <h2>Selected Image</h2>
    <div class="image-wrap">
      <img src="{html.escape(image_reference)}" alt="Selected STEM image">
      <div class="circle" aria-label="AI-suggested suspect circle"></div>
    </div>
    <h2>AI Suggestion</h2>
    <p><strong>Reason:</strong> {html.escape(circle.reason)}</p>
    <p><strong>Confidence:</strong> {html.escape(circle.confidence)}</p>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    return report_path


def write_photo_bundle_report(
    *,
    workspace: Path,
    case_folder: Path,
    case_background: str,
    bundles: tuple[PhotoBundle, ...],
    batch_results: tuple[PhotoBundleBatchResult, ...],
    covered_source_ids: tuple[str, ...],
    evidence_items: tuple[AttachmentEvidence, ...],
    candidate_source_ids: tuple[str, ...] = (),
    candidate_review_results: tuple[FaStemCandidateReviewResult, ...] = (),
    final_ranking: FaStemFinalRanking | None = None,
    first_pass_model_outputs: tuple[str, ...] = (),
    candidate_review_model_outputs: tuple[str, ...] = (),
    final_ranking_model_output: str = "",
) -> Path:
    report_path = case_folder / REPORT_FILE_NAME
    artifact_dir = report_artifact_dir(case_folder)
    assets_dir = artifact_dir / _REPORT_ASSET_DIR_NAME
    assets_dir.mkdir(parents=True, exist_ok=True)
    _write_report_css(assets_dir / "report.css")

    flagged_source_ids = _flagged_source_ids(final_ranking)
    not_flagged_source_ids = tuple(source_id for source_id in covered_source_ids if source_id not in flagged_source_ids)
    _write_report_artifacts(
        artifact_dir=artifact_dir,
        bundles=bundles,
        batch_results=batch_results,
        covered_source_ids=covered_source_ids,
        evidence_items=evidence_items,
        candidate_source_ids=candidate_source_ids,
        candidate_review_results=candidate_review_results,
        final_ranking=final_ranking,
        not_flagged_source_ids=not_flagged_source_ids,
        case_background=case_background,
        first_pass_model_outputs=first_pass_model_outputs,
        candidate_review_model_outputs=candidate_review_model_outputs,
        final_ranking_model_output=final_ranking_model_output,
    )

    bundle_items = _render_bundle_items(case_folder=case_folder, bundles=bundles)
    coverage_items = _render_source_items(covered_source_ids)
    candidate_review_items = _render_candidate_review_items(candidate_review_results)
    not_flagged_items = _render_source_items(not_flagged_source_ids)
    primary_section = _render_primary_suspect_section(
        workspace=workspace,
        case_folder=case_folder,
        final_ranking=final_ranking,
    )
    profile_section = _render_profile_anomaly_section(
        workspace=workspace,
        case_folder=case_folder,
        final_ranking=final_ranking,
    )
    primary_status = "not ranked"
    if final_ranking is not None:
        primary_status = final_ranking.primary_suspect.status
    report_path.write_text(
        f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>FA STEM Suspect Triage Report</title>
  <link rel="stylesheet" href="{html.escape(REPORT_ARTIFACT_DIR_NAME + '/' + _REPORT_ASSET_DIR_NAME + '/report.css')}">
</head>
<body>
  <main>
    <h1>FA STEM Suspect Triage Report</h1>
    <p class="note">These overlays are AI-suggested triage markers, not measurement-grade annotations and not final FA conclusions.</p>
    <h2>Case Background</h2>
    <p>{html.escape(case_background)}</p>

    <h2>Scan Summary</h2>
    <ul>
      <li>Total source images: {len(covered_source_ids)}</li>
      <li>Photo Bundles: {len(bundles)}</li>
      <li>Candidate original-image reviews: {len(candidate_review_results)}</li>
      <li>Primary suspect status: {html.escape(primary_status)}</li>
      <li>Profile anomalies: {0 if final_ranking is None else len(final_ranking.profile_anomalies)}</li>
    </ul>

    <h2>Batch Coverage</h2>
    <ul>
{bundle_items}
    </ul>

    <h2>Covered Source Images</h2>
    <ul>
{coverage_items}
    </ul>

    <h2>Candidate Review Summary</h2>
    <ul>
{candidate_review_items}
    </ul>

{primary_section}

{profile_section}

    <h2>Not-Flagged Images</h2>
    <p>Images below were covered by the scan but were not selected as the primary suspect or profile anomalies in the final ranking.</p>
    <ul>
{not_flagged_items}
    </ul>

    <h2>Uncertainty</h2>
    <p>Use this report as discussion material. Review uncertainty notes before deciding whether any marker deserves destructive analysis or additional imaging.</p>

    <h2>Recommended Next Actions</h2>
    <ol>
      <li>Open the original image for any selected primary electrical suspect and verify the marked region manually.</li>
      <li>Compare profile anomalies against known-good or neighboring structures before treating them as electrical evidence.</li>
      <li>Use not-flagged image accounting to confirm the scan covered the expected STEM folder.</li>
    </ol>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    return report_path


def _write_report_artifacts(
    *,
    artifact_dir: Path,
    bundles: tuple[PhotoBundle, ...],
    batch_results: tuple[PhotoBundleBatchResult, ...],
    covered_source_ids: tuple[str, ...],
    evidence_items: tuple[AttachmentEvidence, ...],
    candidate_source_ids: tuple[str, ...],
    candidate_review_results: tuple[FaStemCandidateReviewResult, ...],
    final_ranking: FaStemFinalRanking | None,
    not_flagged_source_ids: tuple[str, ...],
    case_background: str,
    first_pass_model_outputs: tuple[str, ...],
    candidate_review_model_outputs: tuple[str, ...],
    final_ranking_model_output: str,
) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "case_background": case_background,
        "covered_source_ids": list(covered_source_ids),
        "candidate_source_ids": list(candidate_source_ids),
        "not_flagged_source_ids": list(not_flagged_source_ids),
        "bundles": [_bundle_to_dict(bundle) for bundle in bundles],
        "batch_results": [
            {
                "bundle_path": result.bundle.path.relative_to(artifact_dir).as_posix(),
                "covered_source_ids": list(result.covered_source_ids),
                "evidence_items": [evidence.to_dict() for evidence in result.evidence_items],
            }
            for result in batch_results
        ],
        "first_pass_evidence": [evidence.to_dict() for evidence in evidence_items],
        "candidate_review_results": [_candidate_review_to_dict(review) for review in candidate_review_results],
        "final_ranking": _final_ranking_to_dict(final_ranking),
    }
    (artifact_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    model_outputs = {
        "first_pass": list(first_pass_model_outputs),
        "candidate_reviews": list(candidate_review_model_outputs),
        "final_ranking": final_ranking_model_output,
    }
    (artifact_dir / "model-outputs.json").write_text(
        json.dumps(model_outputs, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_report_css(path: Path) -> None:
    path.write_text(
        """body {
  margin: 0;
  padding: 24px;
  font-family: Arial, sans-serif;
  color: #151515;
  background: #f5f5f5;
}
main {
  max-width: 1120px;
  margin: 0 auto;
}
.note {
  color: #555;
}
.finding-card {
  margin: 16px 0 24px;
  padding: 16px;
  border: 1px solid #d8d8d8;
  background: #ffffff;
}
.image-wrap {
  position: relative;
  display: inline-block;
  max-width: 100%;
  background: #111111;
}
.image-wrap img {
  display: block;
  max-width: 100%;
  height: auto;
}
.overlay-circle {
  position: absolute;
  aspect-ratio: 1;
  border-width: 3px;
  border-style: solid;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-sizing: border-box;
  pointer-events: none;
}
.overlay-circle.primary-suspect {
  border-color: #d31f1f;
}
.overlay-circle.profile-anomaly {
  border-color: #f0b429;
}
""",
        encoding="utf-8",
    )


def _bundle_to_dict(bundle: PhotoBundle) -> dict[str, object]:
    return {
        "path": bundle.path.as_posix(),
        "tiles": [
            {
                "label": tile.label,
                "source_id": tile.source_id,
            }
            for tile in bundle.tiles
        ],
    }


def _candidate_review_to_dict(review: FaStemCandidateReviewResult) -> dict[str, object]:
    return {
        "source_id": review.source_id,
        "observation": review.observation,
        "reason": review.reason,
        "uncertainty": review.uncertainty,
        "confidence": review.confidence,
        "classification": review.classification,
        "coordinates": [dict(coordinate) for coordinate in review.coordinates],
    }


def _final_ranking_to_dict(final_ranking: FaStemFinalRanking | None) -> dict[str, object] | None:
    if final_ranking is None:
        return None
    return {
        "primary_suspect": _final_finding_to_dict(final_ranking.primary_suspect),
        "profile_anomalies": [_final_finding_to_dict(anomaly) for anomaly in final_ranking.profile_anomalies],
    }


def _final_finding_to_dict(finding: FaStemFinalFinding) -> dict[str, object]:
    return {
        "status": finding.status,
        "source_id": finding.source_id,
        "reason": finding.reason,
        "uncertainty": finding.uncertainty,
        "confidence": finding.confidence,
        "coordinates": [dict(coordinate) for coordinate in finding.coordinates],
    }


def _render_bundle_items(*, case_folder: Path, bundles: tuple[PhotoBundle, ...]) -> str:
    if not bundles:
        return "      <li>No Photo Bundles generated.</li>"
    return "\n".join(
        f"      <li>{html.escape(bundle.path.relative_to(case_folder.resolve()).as_posix())}: "
        + html.escape(", ".join(tile.source_id for tile in bundle.tiles))
        + "</li>"
        for bundle in bundles
    )


def _render_source_items(source_ids: tuple[str, ...]) -> str:
    if not source_ids:
        return "      <li>None.</li>"
    return "\n".join(f"      <li>{html.escape(source_id)}</li>" for source_id in source_ids)


def _render_candidate_review_items(candidate_review_results: tuple[FaStemCandidateReviewResult, ...]) -> str:
    if not candidate_review_results:
        return "      <li>No candidate original-image reviews were produced.</li>"
    return "\n".join(
        "      <li>"
        + html.escape(
            f"{review.source_id}: {review.classification}; {review.reason} "
            f"(confidence: {review.confidence}; uncertainty: {review.uncertainty})"
        )
        + "</li>"
        for review in candidate_review_results
    )


def _render_primary_suspect_section(
    *,
    workspace: Path,
    case_folder: Path,
    final_ranking: FaStemFinalRanking | None,
) -> str:
    if final_ranking is None:
        return """
    <h2>Primary Electrical Suspect</h2>
    <p>Final ranking was not produced.</p>"""
    primary = final_ranking.primary_suspect
    if primary.status == "unclear" or primary.source_id is None:
        return f"""
    <h2>Primary Electrical Suspect</h2>
    <p><strong>primary suspect unclear</strong></p>
    <p>{html.escape(primary.reason)}</p>
    <p><strong>Uncertainty:</strong> {html.escape(primary.uncertainty)}</p>
    <p><strong>Confidence:</strong> {html.escape(primary.confidence)}</p>"""
    return """
    <h2>Primary Electrical Suspect</h2>
""" + _render_finding_card(
        workspace=workspace,
        case_folder=case_folder,
        finding=primary,
        title="Primary Electrical Suspect",
        circle_class="primary-suspect",
    )


def _render_profile_anomaly_section(
    *,
    workspace: Path,
    case_folder: Path,
    final_ranking: FaStemFinalRanking | None,
) -> str:
    if final_ranking is None or not final_ranking.profile_anomalies:
        return """
    <h2>Profile Anomalies</h2>
    <p>No profile anomalies were selected in the final ranking.</p>"""
    cards = "\n".join(
        _render_finding_card(
            workspace=workspace,
            case_folder=case_folder,
            finding=anomaly,
            title="Profile Anomaly",
            circle_class="profile-anomaly",
        )
        for anomaly in final_ranking.profile_anomalies
    )
    return f"""
    <h2>Profile Anomalies</h2>
{cards}"""


def _render_finding_card(
    *,
    workspace: Path,
    case_folder: Path,
    finding: FaStemFinalFinding,
    title: str,
    circle_class: str,
) -> str:
    source_id = finding.source_id or ""
    image_reference = _source_image_reference(
        workspace=workspace,
        case_folder=case_folder,
        source_id=source_id,
    )
    marker = _render_overlay_marker(finding.coordinates, circle_class)
    return f"""    <section class="finding-card">
      <h3>{html.escape(title)}: {html.escape(source_id)}</h3>
      <div class="image-wrap">
        <img src="{html.escape(image_reference)}" alt="{html.escape(source_id)}">
{marker}
      </div>
      <p><strong>Reason:</strong> {html.escape(finding.reason)}</p>
      <p><strong>Uncertainty:</strong> {html.escape(finding.uncertainty)}</p>
      <p><strong>Confidence:</strong> {html.escape(finding.confidence)}</p>
    </section>"""


def _source_image_reference(*, workspace: Path, case_folder: Path, source_id: str) -> str:
    source_path = resolve_workspace_path(workspace, source_id)
    try:
        return source_path.relative_to(case_folder.resolve()).as_posix()
    except ValueError:
        return workspace_relative_path(workspace, source_path)


def _render_overlay_marker(coordinates: tuple[dict[str, object], ...], circle_class: str) -> str:
    if not coordinates:
        return "        <p>No marker coordinates were provided.</p>"
    coordinate = coordinates[0]
    center_x = _coordinate_percent(coordinate.get("center_x_percent"))
    center_y = _coordinate_percent(coordinate.get("center_y_percent"))
    radius = _coordinate_percent(coordinate.get("radius_percent"))
    return (
        f'        <div class="overlay-circle {circle_class}" '
        f'style="left: {center_x:.1f}%; top: {center_y:.1f}%; width: {radius * 2:.1f}%;" '
        'aria-label="AI-suggested triage marker"></div>'
    )


def _coordinate_percent(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _flagged_source_ids(final_ranking: FaStemFinalRanking | None) -> set[str]:
    if final_ranking is None:
        return set()
    source_ids = {anomaly.source_id for anomaly in final_ranking.profile_anomalies if anomaly.source_id is not None}
    primary = final_ranking.primary_suspect
    if primary.status == "selected" and primary.source_id is not None:
        source_ids.add(primary.source_id)
    return source_ids
