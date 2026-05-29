from __future__ import annotations

import html
import json
from pathlib import Path

from atlas.attachment_evidence import AttachmentEvidence
from atlas.fa_stem_bundles import REPORT_ARTIFACT_DIR_NAME, PhotoBundle, report_artifact_dir
from atlas.fa_stem_models import (
    FaStemCandidateReviewResult,
    FaStemCircle,
    FaStemFinalFinding,
    FaStemFinalRanking,
    PhotoBundleBatchResult,
)
from atlas.workspace_paths import resolve_workspace_path, workspace_relative_path


_REPORT_ASSET_DIR_NAME = "assets"
REPORT_FILE_NAME = "atlas-fa-stem-brief.html"


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
