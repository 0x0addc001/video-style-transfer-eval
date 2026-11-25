#!/usr/bin/env python3
"""Compose one grouped case-study image per source video (source + all styles)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
STYLE_ZH = {
    "ghibli": "吉卜力", "van_gogh": "梵高", "sketch": "素描", "watercolor": "水彩",
    "monet": "莫奈", "paper_cutting": "剪纸", "american_cartoon": "美式卡通",
    "irasutoya": "Irasutoya 插画", "jojo": "JoJo", "ukiyo_e": "浮世绘",
    "simpsons": "辛普森", "3d_chibi": "3D Q 版",
}
SOURCE_BOX = (88, 65, 1270, 245)
OUTPUT_BOX = (88, 255, 1270, 435)


def style_label(style: str) -> str:
    key = style.lower().replace(" ", "_").replace("-", "_")
    return STYLE_ZH.get(key, style)


def compose(video: str, entries: list[tuple[str, Path]], out_path: Path) -> None:
    width = 1600
    margin = 24
    font = ImageFont.truetype(FONT, 20)
    small = ImageFont.truetype(FONT, 15)
    source = Image.open(entries[0][1]).crop(SOURCE_BOX)
    source_w = width - 2 * margin
    source_h = round(source.height * source_w / source.width)
    cols, rows = 4, 3
    gap = 14
    cell_w = (source_w - (cols - 1) * gap) // cols
    strip_h = 92
    row_h = strip_h + 26
    height = margin + 26 + source_h + 26 + rows * row_h + margin
    canvas = Image.new("RGB", (width, height), "#f6f8fb")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, margin - 2), f"SOURCE · {video}", font=font, fill="#123e4a")
    top = margin + 26
    canvas.paste(source.resize((source_w, source_h)), (margin, top))
    grid_top = top + source_h + 30
    for index, (style, path) in enumerate(entries):
        row, col = divmod(index, cols)
        x = margin + col * (cell_w + gap)
        y = grid_top + row * row_h
        draw.text((x, y), style_label(style), font=small, fill="#1d5c63")
        strip = Image.open(path).crop(OUTPUT_BOX)
        strip = strip.resize((cell_w, strip_h))
        canvas.paste(strip, (x, y + 22))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, quality=92)
    print("wrote", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    out_dir = args.out_dir or (args.metrics.parent / "case_groups")
    groups: dict[str, list[tuple[str, Path]]] = {}
    for case in metrics["cases"]:
        source = Path(case["source_video"])
        sheet = case.get("contact_sheet")
        if not sheet:
            continue
        groups.setdefault(source.stem, []).append((case["style_id"], Path(sheet)))
    for video, entries in sorted(groups.items()):
        entries.sort(key=lambda item: style_label(item[0]))
        compose(video, entries, Path(out_dir) / f"{video}.jpg")


if __name__ == "__main__":
    main()
