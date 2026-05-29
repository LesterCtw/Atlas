from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AttachmentEvidence:
    source_id: str
    observation: str
    inference: str
    uncertainty: str
    confidence: str
    coordinates: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "source_id",
            "observation",
            "inference",
            "uncertainty",
            "confidence",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required.")

        normalized_coordinates = tuple(dict(coordinate) for coordinate in self.coordinates)
        object.__setattr__(self, "coordinates", normalized_coordinates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "observation": self.observation,
            "inference": self.inference,
            "uncertainty": self.uncertainty,
            "confidence": self.confidence,
            "coordinates": [dict(coordinate) for coordinate in self.coordinates],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AttachmentEvidence:
        coordinates = payload.get("coordinates", ())
        if coordinates is None:
            coordinates = ()
        if not isinstance(coordinates, Sequence) or isinstance(coordinates, (str, bytes)):
            raise ValueError("coordinates must be a sequence of objects.")
        if not all(isinstance(coordinate, Mapping) for coordinate in coordinates):
            raise ValueError("coordinates must be a sequence of objects.")

        return cls(
            source_id=str(payload.get("source_id") or ""),
            observation=str(payload.get("observation") or ""),
            inference=str(payload.get("inference") or ""),
            uncertainty=str(payload.get("uncertainty") or ""),
            confidence=str(payload.get("confidence") or ""),
            coordinates=tuple(dict(coordinate) for coordinate in coordinates),
        )


def format_saved_attachment_evidence(evidence_items: Sequence[AttachmentEvidence]) -> str:
    if not evidence_items:
        return "Saved attachment evidence:\nDo not assume prior attachments are still visible.\nNone."

    sections = ["Saved attachment evidence:\nDo not assume prior attachments are still visible."]
    for index, evidence in enumerate(evidence_items, start=1):
        section = [
            f"Evidence {index}:",
            f"Source: {evidence.source_id}",
            f"Observation: {evidence.observation}",
            f"Inference: {evidence.inference}",
            f"Uncertainty: {evidence.uncertainty}",
            f"Confidence: {evidence.confidence}",
        ]
        if evidence.coordinates:
            coordinates_json = json.dumps(
                list(evidence.coordinates),
                ensure_ascii=False,
                sort_keys=True,
            )
            section.append(f"Coordinates: {coordinates_json}")
        else:
            section.append("Coordinates: none")
        sections.append("\n".join(section))
    return "\n\n".join(sections)
