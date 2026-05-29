from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw, ImageOps

from atlas.attachment_evidence import AttachmentEvidence, format_saved_attachment_evidence


_JSON_FENCE_PATTERN = re.compile(r"```json\s*(.*?)```", re.DOTALL)
_SUPPORTED_STEM_SUFFIXES = frozenset({".jpg", ".jpeg"})
_PHOTO_BUNDLE_DIR_NAME = "atlas-fa-stem-bundles"
_PHOTO_BUNDLE_TILE_SIZE = 256
REPORT_FILE_NAME = "atlas-fa-stem-brief.html"


class FaStemConversation(Protocol):
    async def send_single_turn(self, user_prompt: str) -> str:
        pass

    async def attach_file(self, path: Path) -> None:
        pass


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
class FaStemBriefResult:
    report_path: Path
    selected_image: Path
    bundles: tuple[PhotoBundle, ...]
    batch_results: tuple[PhotoBundleBatchResult, ...]
    covered_source_ids: tuple[str, ...]
    evidence_items: tuple[AttachmentEvidence, ...]
    status_events: list[str]

    @property
    def evidence(self) -> AttachmentEvidence:
        if not self.evidence_items:
            raise FaStemBriefError("No FA STEM candidate evidence was recorded.")
        return self.evidence_items[0]


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

    covered_source_ids = tuple(image.relative_to(workspace.resolve()).as_posix() for image in images)
    status_events.append("writing-fa-stem-report")
    report_path = write_photo_bundle_report(
        case_folder=case_folder,
        case_background=case_background,
        bundles=bundles,
        covered_source_ids=covered_source_ids,
        evidence_items=tuple(evidence_items),
    )
    return FaStemBriefResult(
        report_path=report_path,
        selected_image=images[0],
        bundles=bundles,
        batch_results=tuple(batch_results),
        covered_source_ids=covered_source_ids,
        evidence_items=tuple(evidence_items),
        status_events=status_events,
    )


@dataclass(frozen=True)
class PhotoBundleTile:
    label: str
    source_id: str
    source_path: Path


@dataclass(frozen=True)
class PhotoBundle:
    path: Path
    tiles: tuple[PhotoBundleTile, ...]


@dataclass(frozen=True)
class PhotoBundleBatchResult:
    bundle: PhotoBundle
    covered_source_ids: tuple[str, ...]
    evidence_items: tuple[AttachmentEvidence, ...]


def select_single_stem_image(case_folder: Path) -> Path:
    images = collect_stem_images(case_folder)
    if not images:
        raise FaStemBriefError("No .jpg or .jpeg image found in the selected folder.")
    return images[0].resolve()


def collect_stem_images(case_folder: Path) -> tuple[Path, ...]:
    resolved_folder = case_folder.resolve()
    images = (
        child.resolve()
        for child in resolved_folder.rglob("*")
        if child.is_file() and child.suffix.lower() in _SUPPORTED_STEM_SUFFIXES
    )
    return tuple(
        sorted(
            images,
            key=lambda item: item.relative_to(resolved_folder).as_posix().lower(),
        )
    )


def create_photo_bundles(
    *,
    workspace: Path,
    case_folder: Path,
    images: tuple[Path, ...],
) -> tuple[PhotoBundle, ...]:
    output_dir = case_folder / _PHOTO_BUNDLE_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)

    bundles: list[PhotoBundle] = []
    for batch_index, batch in enumerate(_chunks(images, 9), start=1):
        bundle_path = output_dir / f"photo-bundle-{batch_index:03d}.png"
        tiles = tuple(
            PhotoBundleTile(
                label=_tile_label(index),
                source_id=image.relative_to(workspace.resolve()).as_posix(),
                source_path=image,
            )
            for index, image in enumerate(batch)
        )
        _write_photo_bundle(bundle_path, tiles)
        bundles.append(PhotoBundle(path=bundle_path, tiles=tiles))
    return tuple(bundles)


def _chunks(images: tuple[Path, ...], size: int) -> tuple[tuple[Path, ...], ...]:
    return tuple(tuple(images[index : index + size]) for index in range(0, len(images), size))


def _tile_label(index: int) -> str:
    row = "ABC"[index // 3]
    column = (index % 3) + 1
    return f"{row}{column}"


def _write_photo_bundle(bundle_path: Path, tiles: tuple[PhotoBundleTile, ...]) -> None:
    tile_size = _PHOTO_BUNDLE_TILE_SIZE
    canvas = Image.new("RGB", (tile_size * 3, tile_size * 3), "white")
    draw = ImageDraw.Draw(canvas)

    for index, tile in enumerate(tiles):
        row = index // 3
        column = index % 3
        left = column * tile_size
        top = row * tile_size
        with Image.open(tile.source_path) as source:
            thumbnail = ImageOps.contain(source.convert("RGB"), (tile_size, tile_size))
        paste_left = left + (tile_size - thumbnail.width) // 2
        paste_top = top + (tile_size - thumbnail.height) // 2
        canvas.paste(thumbnail, (paste_left, paste_top))
        draw.rectangle((left, top, left + tile_size - 1, top + tile_size - 1), outline="black", width=2)
        draw.rectangle((left + 4, top + 4, left + 44, top + 28), fill="white", outline="black")
        draw.text((left + 10, top + 9), tile.label, fill="black")

    canvas.save(bundle_path)


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


def _parse_fenced_json_object(model_response: str) -> dict[str, object]:
    matches = _JSON_FENCE_PATTERN.findall(model_response)
    if not matches:
        raise FaStemBriefError("tGenie response did not include a fenced JSON block.")
    try:
        payload = json.loads(matches[0])
    except json.JSONDecodeError as error:
        raise FaStemBriefError("tGenie response included malformed JSON.") from error
    if not isinstance(payload, dict):
        raise FaStemBriefError("tGenie JSON response must be an object.")
    return payload


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
    image_reference = image_path.relative_to(workspace.resolve()).as_posix()
    folder_reference = case_folder.relative_to(workspace.resolve()).as_posix()
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
    matches = _JSON_FENCE_PATTERN.findall(model_response)
    if not matches:
        raise FaStemBriefError("tGenie response did not include a fenced JSON block.")
    try:
        payload = json.loads(matches[0])
    except json.JSONDecodeError as error:
        raise FaStemBriefError("tGenie response included malformed JSON.") from error
    if not isinstance(payload, dict):
        raise FaStemBriefError("tGenie JSON response must be an object.")

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
    case_folder: Path,
    case_background: str,
    bundles: tuple[PhotoBundle, ...],
    covered_source_ids: tuple[str, ...],
    evidence_items: tuple[AttachmentEvidence, ...],
) -> Path:
    report_path = case_folder / REPORT_FILE_NAME
    bundle_items = "\n".join(
        f"      <li>{html.escape(bundle.path.relative_to(case_folder.resolve()).as_posix())}: "
        + html.escape(", ".join(tile.source_id for tile in bundle.tiles))
        + "</li>"
        for bundle in bundles
    )
    coverage_items = "\n".join(f"      <li>{html.escape(source_id)}</li>" for source_id in covered_source_ids)
    evidence_text = format_saved_attachment_evidence(evidence_items)
    report_path.write_text(
        f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>FA STEM Brief First-Pass Report</title>
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
    pre {{
      white-space: pre-wrap;
      background: #ffffff;
      padding: 16px;
      border: 1px solid #d8d8d8;
    }}
    .note {{
      color: #555;
    }}
  </style>
</head>
<body>
  <main>
    <h1>FA STEM Brief First-Pass Report</h1>
    <p class="note">This report records first-pass candidate observations, not final FA conclusions.</p>
    <h2>Case Background</h2>
    <p>{html.escape(case_background)}</p>
    <h2>Photo Bundles</h2>
    <ul>
{bundle_items}
    </ul>
    <h2>Covered Source Images</h2>
    <ul>
{coverage_items}
    </ul>
    <h2>Saved Attachment Evidence</h2>
    <pre>{html.escape(evidence_text)}</pre>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    return report_path
