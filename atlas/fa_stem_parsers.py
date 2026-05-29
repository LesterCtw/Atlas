from __future__ import annotations

from atlas.attachment_evidence import AttachmentEvidence
from atlas.fa_stem_bundles import PhotoBundle
from atlas.fa_stem_models import (
    FaStemBriefError,
    FaStemCandidateReviewResult,
    FaStemCircle,
    FaStemFinalFinding,
    FaStemFinalRanking,
)
from atlas.json_fences import (
    JsonFencePayloadError,
    MalformedJsonFenceError,
    MissingJsonFenceError,
    parse_first_json_fence_object,
)


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
