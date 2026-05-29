from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from atlas.attachment_evidence import AttachmentEvidence
from atlas.fa_stem_bundles import PhotoBundle


class FaStemBriefError(RuntimeError):
    pass


@dataclass(frozen=True)
class FaStemCircle:
    center_x_percent: float
    center_y_percent: float
    radius_percent: float
    observation: str
    inference: str
    uncertainty: str
    confidence: str

    @property
    def reason(self) -> str:
        return self.inference


@dataclass(frozen=True)
class FaStemCandidateReviewResult:
    source_id: str
    observation: str
    reason: str
    uncertainty: str
    confidence: str
    classification: str
    coordinates: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class FaStemFinalFinding:
    status: str
    source_id: str | None
    reason: str
    uncertainty: str
    confidence: str
    coordinates: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class FaStemFinalRanking:
    primary_suspect: FaStemFinalFinding
    profile_anomalies: tuple[FaStemFinalFinding, ...]


@dataclass(frozen=True)
class PhotoBundleBatchResult:
    bundle: PhotoBundle
    covered_source_ids: tuple[str, ...]
    evidence_items: tuple[AttachmentEvidence, ...]


@dataclass(frozen=True)
class FaStemBriefResult:
    report_path: Path
    artifact_dir: Path
    selected_image: Path
    bundles: tuple[PhotoBundle, ...]
    batch_results: tuple[PhotoBundleBatchResult, ...]
    covered_source_ids: tuple[str, ...]
    evidence_items: tuple[AttachmentEvidence, ...]
    candidate_source_ids: tuple[str, ...]
    candidate_review_results: tuple[FaStemCandidateReviewResult, ...]
    final_ranking: FaStemFinalRanking
    status_events: list[str]

    @property
    def evidence(self) -> AttachmentEvidence:
        if not self.evidence_items:
            raise FaStemBriefError("No FA STEM candidate evidence was recorded.")
        return self.evidence_items[0]
