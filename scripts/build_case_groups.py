#!/usr/bin/env python3
"""One grouped case image per source video: 3 source frames + 12 styles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
STYLE_ZH = {
    "ghibli": "吉卜力", "van_gogh": "梵高", "sketch": "素描", "watercolor": "水彩",
    "monet": "莫奈", "paper_cutting": "剪纸", "american_cartoon": "美式卡通",
    "irasutoya": "Irasutoya 插画", "jojo": "JoJo", "ukiyo_e": "浮世绘",
    "simpsons": "辛普森", "3d_chibi": "3D Q 版",
}


def style_label(style: str) -> str:
    key = style.lower().replace(" ", "_").replace("-", "_")
    return STYLE_ZH.get(key, style)


def sample_frames(path: Path, count: int, width: int, height: int) -> list[Image.Image]:
    capture = cv2.VideoCapture(str(path))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    frames: list[Image.Image] = []
    if total > 0:
        for index in np.linspace(0, max(total - 1, 0), count).astype(int):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb).resize((width, height), Image.LANCZOS))
    capture.release()
    return frames


def compose(video: str, source: Path, entries: list[tuple[str, Path]], out_path: Path) -> None:
    frame_w, frame_h = 150, 84
    cols = 3
    rows = max(1, (len(entries) + cols - 1) // cols)
    gap = 6
    col_gap = 18
    margin = 24
    label_font = ImageFont.truetype(FONT, 18)
    small_font = ImageFont.truetype(FONT, 15)
    col_w = 3 * frame_w + 2 * gap
    width = 2 * margin + cols * col_w + (cols - 1) * col_gap
    grid_top = margin + 28 + frame_h + 22
    row_h = frame_h + 28
    height = grid_top + rows * row_h + margin
    canvas = Image.new("RGB", (width, height), "#f6f8fb")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, margin - 2), f"SOURCE · {video}", font=label_font, fill="#123e4a")
    x = margin
    for frame in sample_frames(source, 3, frame_w, frame_h):
        canvas.paste(frame, (x, margin + 26))
        x += frame_w + gap
    for index, (style, output) in enumerate(entries):
        row, col = divmod(index, cols)
        cell_x = margin + col * (col_w + col_gap)
        y = grid_top + row * row_h
        draw.text((cell_x, y), style_label(style), font=small_font, fill="#1d5c63")
        for frame_index, frame in enumerate(sample_frames(output, 3, frame_w, frame_h)):
            canvas.paste(frame, (cell_x + frame_index * (frame_w + gap), y + 22))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, quality=93)
    print("wrote", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    out_dir = args.out_dir or (args.metrics.parent / "case_groups")
    groups: dict[str, list[tuple[str, Path]]] = {}
    sources: dict[str, Path] = {}
    for case in metrics["cases"]:
        source = Path(case["source_video"])
        method_id = next(iter(case.get("methods", {})), None)
        output = case["methods"][method_id].get("video") if method_id else None
        if not output:
            continue
        groups.setdefault(source.stem, []).append((case["style_id"], Path(output)))
        sources[source.stem] = source
    manifest = []
    for video, entries in sorted(groups.items()):
        entries.sort(key=lambda item: style_label(item[0]))
        name = f"{video}.jpg"
        compose(video, sources[video], entries, Path(out_dir) / name)
        manifest.append({"video": video, "image": name})
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
