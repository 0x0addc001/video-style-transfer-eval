#!/usr/bin/env python3
"""Compose one grouped case-study image per source video from the actual videos."""

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
        indices = np.linspace(0, max(total - 1, 0), count).astype(int)
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb).resize((width, height), Image.LANCZOS))
    capture.release()
    return frames


def compose(video: str, source: Path, entries: list[tuple[str, Path]], out_path: Path) -> None:
    width, margin, gap = 1600, 24, 12
    frame_w, frame_h = 306, 172        # source frames (5 across)
    cell_w, cell_h = 170, 96           # style frames (3 across, 3 columns)
    label_font = ImageFont.truetype(FONT, 17)
    small_font = ImageFont.truetype(FONT, 15)

    cols, rows = 3, 2
    grid_w = width - 2 * margin
    source_total = 5 * frame_w + 4 * gap
    grid_top = margin + 26 + frame_h + 26
    row_h = cell_h + 26
    height = grid_top + rows * row_h + margin + 10
    canvas = Image.new("RGB", (width, height), "#f6f8fb")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, margin - 2), f"SOURCE · {video}", font=label_font, fill="#123e4a")

    x = margin
    for frame in sample_frames(source, 5, frame_w, frame_h):
        canvas.paste(frame, (x, margin + 26))
        x += frame_w + gap

    for index, (style, output) in enumerate(entries):
        row, col = divmod(index, cols)
        col_w = (grid_w - (cols - 1) * 14) // cols
        x = margin + col * (col_w + 14)
        y = grid_top + row * row_h
        draw.text((x, y), style_label(style), font=small_font, fill="#1d5c63")
        strip = sample_frames(output, 3, cell_w, cell_h)
        for frame_index, frame in enumerate(strip):
            canvas.paste(frame, (x + frame_index * (cell_w + 6), y + 22))
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
    for video, entries in sorted(groups.items()):
        entries.sort(key=lambda item: style_label(item[0]))
        chunks = [entries[start:start + 6] for start in range(0, len(entries), 6)]
        for part, chunk in enumerate(chunks, start=1):
            label = f"{video}（{part}/{len(chunks)}）" if len(chunks) > 1 else video
            name = f"{video}__{part}.jpg" if len(chunks) > 1 else f"{video}.jpg"
            compose(label, sources[video], chunk, Path(out_dir) / name)


if __name__ == "__main__":
    main()
