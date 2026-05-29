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
from atlas.fa_stem_parsers import (
    build_fa_stem_evidence,
    parse_candidate_review_result,
    parse_fa_stem_circle,
    parse_final_ranking,
    parse_photo_bundle_candidate_evidence,
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


def select_candidate_source_ids(evidence_items: tuple[AttachmentEvidence, ...]) -> tuple[str, ...]:
    selected: list[str] = []
    for evidence in evidence_items:
        if evidence.source_id not in selected:
            selected.append(evidence.source_id)
        if len(selected) == _MAX_CANDIDATE_REVIEWS:
            break
    return tuple(selected)
