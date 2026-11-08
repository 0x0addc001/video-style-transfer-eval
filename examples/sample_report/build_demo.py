#!/usr/bin/env python3
"""Build a clearly labeled synthetic dataset for demonstrating the evaluation skill."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


WIDTH = 384
HEIGHT = 216
FPS = 20
FRAMES = 60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "demo_run")
    return parser.parse_args()


def write_video(path: Path, frames: list[np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (WIDTH, HEIGHT),
    )
    if not writer.isOpened():
        raise RuntimeError(f"Cannot create video writer for {path}")
    for frame in frames:
        writer.write(frame)
    writer.release()


def make_style_images(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    rng = np.random.default_rng(13)
    y, x = np.mgrid[0:512, 0:512]

    palette_sets = [
        [(21, 72, 88), (37, 132, 142), (214, 119, 47), (239, 205, 116)],
        [(42, 35, 95), (104, 55, 148), (203, 69, 139), (249, 183, 73)],
        [(35, 82, 58), (101, 143, 83), (193, 160, 68), (235, 222, 172)],
    ]
    for style_index, palette in enumerate(palette_sets):
        image = np.zeros((512, 512, 3), dtype=np.float64)
        for index, color in enumerate(palette):
            wave = np.sin(
                x * (0.018 + index * 0.003)
                + y * (0.010 - index * 0.002)
                + style_index * 1.7
            )
            band = np.clip((wave + 1.0) / 2.0, 0.0, 1.0)
            weight = np.clip(1.0 - np.abs(band - 0.52) * 2.6, 0.0, 1.0)
            image += weight[:, :, None] * np.array(color, dtype=np.float64)
        noise = rng.normal(0, 9, size=(512, 512, 1))
        image += noise
        image = np.clip(image, 0, 255)
        image[:256, :256] = cv2.GaussianBlur(image[:256, :256], (0, 0), 2.0)
        image = cv2.addWeighted(
            image.astype(np.uint8),
            0.72,
            cv2.GaussianBlur(image.astype(np.uint8), (0, 0), 1.0),
            0.28,
            0,
        )
        path = output_dir / f"style_{style_index + 1:02d}.jpg"
        cv2.imwrite(str(path), image)
        paths.append(path)
    return paths


def source_frames(case_index: int) -> list[np.ndarray]:
    frames = []
    for frame_index in range(FRAMES):
        progress = frame_index / (FRAMES - 1)
        y, x = np.mgrid[0:HEIGHT, 0:WIDTH]
        background = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        background[:, :, 0] = np.clip(64 + 38 * x / WIDTH, 0, 255)
        background[:, :, 1] = np.clip(80 + 25 * y / HEIGHT, 0, 255)
        background[:, :, 2] = np.clip(96 + 20 * progress, 0, 255)
        image = background.copy()

        if case_index == 0:
            center = (
                int(80 + 225 * (0.5 - 0.5 * math.cos(progress * math.tau))),
                int(112 + 42 * math.sin(progress * math.tau * 1.4)),
            )
            cv2.ellipse(image, center, (46, 32), -14, 0, 360, (225, 229, 235), -1)
            cv2.ellipse(image, center, (46, 32), -14, 0, 360, (40, 54, 64), 3)
            cv2.circle(image, (center[0] + 12, center[1] - 4), 7, (54, 70, 82), -1)
            cv2.line(image, (24, 176), (358, 176), (43, 49, 54), 4)
            cv2.line(
                image,
                (58, 44),
                (int(58 + 180 * progress), 44),
                (232, 214, 161),
                3,
            )
        elif case_index == 1:
            shift = int(-38 + 76 * progress)
            for x_rect in range(-70, 470, 95):
                x0 = x_rect + shift
                cv2.rectangle(
                    image,
                    (x0, 142),
                    (x0 + 64, 186),
                    (62, 77, 93),
                    -1,
                )
                cv2.rectangle(
                    image,
                    (x0 + 8, 152),
                    (x0 + 23, 170),
                    (202, 206, 188),
                    -1,
                )
            ball_x = int(54 + 275 * progress)
            ball_y = int(104 + 35 * math.sin(progress * math.tau))
            cv2.circle(image, (ball_x, ball_y), 19, (236, 144, 59), -1)
            cv2.circle(image, (ball_x, ball_y), 19, (58, 52, 46), 2)
            cv2.polylines(
                image,
                [
                    np.array(
                        [
                            [0, int(68 + 12 * math.sin(progress * math.tau))],
                            [95, 56],
                            [190, 73],
                            [286, 51],
                            [384, 66],
                        ],
                        dtype=np.int32,
                    )
                ],
                False,
                (32, 45, 53),
                5,
            )
        else:
            angle = 20 + 170 * progress
            center = (
                int(192 + 94 * math.cos(progress * math.tau)),
                int(108 + 38 * math.sin(progress * math.tau)),
            )
            triangle = cv2.boxPoints((center, (72, 62), angle)).astype(np.int32)
            cv2.fillPoly(image, [triangle], (211, 218, 223))
            cv2.polylines(image, [triangle], True, (36, 47, 57), 3)
            for stem_index in range(3):
                sx = 42 + stem_index * 15
                sway = int(8 * math.sin(progress * math.tau + stem_index))
                cv2.line(
                    image,
                    (sx, 202),
                    (sx + sway, 154),
                    (56, 94, 68),
                    4,
                )
                cv2.circle(
                    image,
                    (sx + sway, 148),
                    9,
                    (88, 146, 92),
                    -1,
                )
        frames.append(image)
    return frames


def transfer_palette(
    source: np.ndarray,
    style: np.ndarray,
    strength: float,
) -> np.ndarray:
    source_lab = cv2.cvtColor(source, cv2.COLOR_BGR2LAB).astype(np.float32)
    style_lab = cv2.cvtColor(style, cv2.COLOR_BGR2LAB).astype(np.float32)
    output = source_lab.copy()
    for channel in range(3):
        source_pixels = source_lab[:, :, channel]
        style_pixels = style_lab[:, :, channel]
        source_mean = float(source_pixels.mean())
        source_std = max(float(source_pixels.std()), 5.0)
        style_mean = float(style_pixels.mean())
        style_std = max(float(style_pixels.std()), 5.0)
        transformed = (
            (source_pixels - source_mean) / source_std * style_std + style_mean
        )
        output[:, :, channel] = (
            source_pixels * (1.0 - strength) + transformed * strength
        )
    return cv2.cvtColor(
        np.clip(output, 0, 255).astype(np.uint8),
        cv2.COLOR_LAB2BGR,
    )


def style_texture(style: np.ndarray) -> np.ndarray:
    texture = cv2.resize(style, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(texture, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (0, 0), 1.2)


def candidate_frames(
    sources: list[np.ndarray],
    style: np.ndarray,
    variant: str,
) -> list[np.ndarray]:
    texture = style_texture(style).astype(np.float32)
    frames = []
    previous = None
    for frame_index, source in enumerate(sources):
        if variant == "balanced":
            styled = transfer_palette(source, style, 0.58)
            gray = cv2.cvtColor(styled, cv2.COLOR_BGR2GRAY).astype(np.float32)
            styled = np.clip(
                gray[:, :, None] * 0.17
                + styled.astype(np.float32) * 0.83
                + (texture[:, :, None] - 128.0) * 0.10,
                0,
                255,
            ).astype(np.uint8)
            if previous is not None:
                styled = cv2.addWeighted(styled, 0.64, previous, 0.36, 0)
        elif variant == "flicker":
            styled = transfer_palette(source, style, 0.80)
            flash = 1.0 + 0.18 * math.sin(frame_index * 1.37)
            shift_x = 2 if frame_index % 2 == 0 else -2
            matrix = np.float32([[1, 0, shift_x], [0, 1, 1]])
            styled = cv2.warpAffine(
                styled,
                matrix,
                (WIDTH, HEIGHT),
                borderMode=cv2.BORDER_REFLECT_101,
            )
            styled = np.clip(
                styled.astype(np.float32) * flash
                + (texture[:, :, None] - 128.0) * 0.22,
                0,
                255,
            ).astype(np.uint8)
        else:
            styled = transfer_palette(source, style, 0.88)
            blur = cv2.GaussianBlur(styled, (0, 0), 2.4)
            styled = cv2.addWeighted(styled, 0.25, blur, 0.75, 0)
            tint = np.array([26, -10, 18], dtype=np.float32)
            styled = np.clip(styled.astype(np.float32) + tint, 0, 255).astype(np.uint8)
            styled = cv2.addWeighted(
                styled,
                0.54,
                cv2.cvtColor(texture.astype(np.uint8), cv2.COLOR_GRAY2BGR),
                0.46,
                0,
            )
        frames.append(styled)
        previous = styled
    return frames


def main() -> None:
    args = parse_args()
    root = args.output.resolve()
    source_dir = root / "data" / "source"
    style_dir = root / "data" / "style"
    output_dir = root / "data" / "outputs"
    styles = make_style_images(style_dir)
    method_configs = [
        ("balanced", "Simulated balanced", 18.4, 12.7),
        ("flicker", "Simulated flicker", 14.6, 9.8),
        ("overlay", "Simulated overlay", 16.1, 10.4),
    ]
    cases = []
    for case_index in range(3):
        case_id = f"demo_case_{case_index + 1:02d}"
        styles_bgr = cv2.imread(str(styles[case_index]), cv2.IMREAD_COLOR)
        sources = source_frames(case_index)
        source_path = source_dir / f"{case_id}.mp4"
        write_video(source_path, sources)
        outputs = {}
        for variant, label, runtime, memory in method_configs:
            output_path = output_dir / variant / f"{case_id}.mp4"
            write_video(output_path, candidate_frames(sources, styles_bgr, variant))
            outputs[variant] = {
                "video": str(output_path.relative_to(root)).replace("\\", "/"),
                "runtime_s": runtime + case_index * 0.4,
                "peak_memory_gb": memory,
            }
        cases.append(
            {
                "id": case_id,
                "content_id": f"content_{case_index + 1:02d}",
                "style_id": f"style_{case_index + 1:02d}",
                "split": "synthetic_demo",
                "source_video": str(source_path.relative_to(root)).replace("\\", "/"),
                "style_image": str(styles[case_index].relative_to(root)).replace("\\", "/"),
                "outputs": outputs,
            }
        )

    manifest = {
        "schema_version": "1.0",
        "experiment": {
            "title": "Synthetic demonstration of video style transfer evaluation",
            "split": "synthetic_demo",
            "frame_limit": 30,
            "max_side": 320,
            "temporal_offsets": [1, 5],
            "hardware": "Synthetic data generation only",
            "notes": (
                "All clips and methods are synthetic. This run demonstrates the "
                "evaluation workflow and is not a benchmark of EchoStyle or a model."
            ),
        },
        "methods": [
            {
                "id": variant,
                "label": label,
                "label_zh": {
                    "balanced": "模拟平衡方法",
                    "flicker": "模拟闪烁方法",
                    "overlay": "模拟覆盖方法",
                }[variant],
                "seed": 42,
                "checkpoint": "synthetic",
            }
            for variant, label, _, _ in method_configs
        ],
        "cases": cases,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(manifest_path)


if __name__ == "__main__":
    main()
