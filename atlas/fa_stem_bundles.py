from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from atlas.workspace_paths import workspace_relative_path


REPORT_ARTIFACT_DIR_NAME = "atlas-fa-stem-report"
_PHOTO_BUNDLE_DIR_NAME = "bundles"
_PHOTO_BUNDLE_TILE_SIZE = 256
_SUPPORTED_STEM_SUFFIXES = frozenset({".jpg", ".jpeg"})


@dataclass(frozen=True)
class PhotoBundleTile:
    label: str
    source_id: str
    source_path: Path


@dataclass(frozen=True)
class PhotoBundle:
    path: Path
    tiles: tuple[PhotoBundleTile, ...]


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
    output_dir = report_artifact_dir(case_folder) / _PHOTO_BUNDLE_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)

    bundles: list[PhotoBundle] = []
    for batch_index, batch in enumerate(_chunks(images, 9), start=1):
        bundle_path = output_dir / f"photo-bundle-{batch_index:03d}.png"
        tiles = tuple(
            PhotoBundleTile(
                label=_tile_label(index),
                source_id=workspace_relative_path(workspace, image),
                source_path=image,
            )
            for index, image in enumerate(batch)
        )
        _write_photo_bundle(bundle_path, tiles)
        bundles.append(PhotoBundle(path=bundle_path, tiles=tiles))
    return tuple(bundles)


def report_artifact_dir(case_folder: Path) -> Path:
    return case_folder / REPORT_ARTIFACT_DIR_NAME


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

    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(bundle_path)
