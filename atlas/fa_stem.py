from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


_JSON_FENCE_PATTERN = re.compile(r"```json\s*(.*?)```", re.DOTALL)
_SUPPORTED_STEM_SUFFIXES = frozenset({".jpg", ".jpeg"})
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
    reason: str
    confidence: str


@dataclass(frozen=True)
class FaStemBriefResult:
    report_path: Path
    selected_image: Path
    status_events: list[str]


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
    selected_image = select_single_stem_image(case_folder)

    try:
        status_events.append("uploading-attachment")
        await conversation.attach_file(selected_image)
        status_events.append("attachment-uploaded")
        status_events.append("waiting-for-model")
        model_response = await conversation.send_single_turn(
            build_single_image_prompt(
                workspace=workspace,
                case_folder=case_folder,
                image_path=selected_image,
                case_background=case_background,
            )
        )
    except Exception as error:
        raise FaStemBriefError(f"FA STEM brief failed while talking to tGenie: {error}") from error

    status_events.append("parsing-fa-stem-response")
    circle = parse_fa_stem_circle(model_response)
    status_events.append("writing-fa-stem-report")
    report_path = write_single_image_report(
        case_folder=case_folder,
        image_path=selected_image,
        case_background=case_background,
        circle=circle,
    )
    return FaStemBriefResult(
        report_path=report_path,
        selected_image=selected_image,
        status_events=status_events,
    )


def select_single_stem_image(case_folder: Path) -> Path:
    images = sorted(
        (
            child
            for child in case_folder.iterdir()
            if child.is_file() and child.suffix.lower() in _SUPPORTED_STEM_SUFFIXES
        ),
        key=lambda item: item.name.lower(),
    )
    if not images:
        raise FaStemBriefError("No .jpg or .jpeg image found in the selected folder.")
    return images[0].resolve()


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
  "reason": "short visual reason",
  "confidence": "low | medium | high"
}}
```

Use percent coordinates relative to the image: x from left to right, y from top to bottom.
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
            "reason",
            "confidence",
        )
        if field not in payload
    ]
    if missing_fields:
        raise FaStemBriefError("tGenie JSON response is missing: " + ", ".join(missing_fields))

    try:
        return FaStemCircle(
            center_x_percent=float(payload["center_x_percent"]),
            center_y_percent=float(payload["center_y_percent"]),
            radius_percent=float(payload["radius_percent"]),
            reason=str(payload["reason"]),
            confidence=str(payload["confidence"]),
        )
    except (TypeError, ValueError) as error:
        raise FaStemBriefError("tGenie JSON coordinates must be numeric percent values.") from error


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
