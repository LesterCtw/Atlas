from __future__ import annotations

from pathlib import Path
from typing import Protocol

from atlas.attachment_evidence import AttachmentEvidence
from atlas.fa_stem_bundles import (
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
from atlas.fa_stem_prompts import (
    build_candidate_review_prompt,
    build_final_ranking_prompt,
    build_photo_bundle_prompt,
    build_single_image_prompt,
    format_candidate_review_evidence,
)
from atlas.json_fences import (
    JsonFencePayloadError,
    MalformedJsonFenceError,
    MissingJsonFenceError,
    parse_first_json_fence_object,
)
from atlas.fa_stem_report import REPORT_FILE_NAME, write_photo_bundle_report, write_single_image_report
from atlas.workspace_paths import workspace_relative_path


_MAX_CANDIDATE_REVIEWS = 10


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
