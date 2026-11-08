#!/usr/bin/env python3
"""Compute paired diagnostic metrics and blinded review packets for VST videos."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


METRIC_INFO = {
    "ssim": {
        "label": "SSIM",
        "dimension": "content",
        "higher_is_better": True,
        "unit": "",
    },
    "psnr": {
        "label": "PSNR",
        "dimension": "content",
        "higher_is_better": True,
        "unit": "dB",
    },
    "lab_palette_w1": {
        "label": "LAB palette W1",
        "dimension": "style",
        "higher_is_better": False,
        "unit": "normalized x100",
    },
    "lab_ab_palette_w1": {
        "label": "LAB chroma palette W1",
        "dimension": "style",
        "higher_is_better": False,
        "unit": "normalized x100",
    },
    "luminance_flicker": {
        "label": "Detrended luminance flicker",
        "dimension": "temporal",
        "higher_is_better": False,
        "unit": "gray levels",
    },
    "runtime_s": {
        "label": "Runtime",
        "dimension": "cost",
        "higher_is_better": False,
        "unit": "s",
    },
    "peak_memory_gb": {
        "label": "Peak GPU memory",
        "dimension": "cost",
        "higher_is_better": False,
        "unit": "GB",
    },
}

SCORE_DIMENSIONS = [
    "style_adherence",
    "content_preservation",
    "temporal_stability",
    "artifact_control",
    "overall_visual_quality",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--blind",
        action="store_true",
        help="Randomize method labels independently for every case.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="Seed for deterministic blinded label assignment.",
    )
    parser.add_argument(
        "--no-contact-sheets",
        action="store_true",
        help="Skip generation of visual review sheets.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(value: str, manifest_dir: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (manifest_dir / path).resolve()


def finite_float(value: float | int | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def mean_or_none(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def read_video_metadata(path: Path) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    if fps <= 0 or frame_count <= 0:
        raise ValueError(f"Video has invalid FPS or frame count: {path}")
    return {
        "fps": fps,
        "frame_count": frame_count,
        "duration_s": frame_count / fps,
        "width": width,
        "height": height,
        "aspect_ratio": width / height if height else None,
    }


def resize_rgb(
    frame_rgb: np.ndarray,
    max_side: int,
    target_wh: tuple[int, int] | None = None,
) -> np.ndarray:
    if target_wh is not None:
        width, height = target_wh
        if (frame_rgb.shape[1], frame_rgb.shape[0]) != (width, height):
            return cv2.resize(frame_rgb, (width, height), interpolation=cv2.INTER_AREA)
        return frame_rgb
    height, width = frame_rgb.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    if scale == 1.0:
        return frame_rgb
    return cv2.resize(
        frame_rgb,
        (max(2, round(width * scale)), max(2, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def read_frames_at_times(
    path: Path,
    times_s: list[float],
    max_side: int,
    target_wh: tuple[int, int] | None = None,
) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    frames: list[np.ndarray] = []
    for timestamp in times_s:
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ok, frame_bgr = cap.read()
        if not ok:
            break
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        frames.append(resize_rgb(frame_rgb, max_side, target_wh))
    cap.release()
    if len(frames) != len(times_s):
        raise ValueError(
            f"Decoded {len(frames)} of {len(times_s)} requested frames from {path}"
        )
    return frames


def sample_times(metadata: dict[str, Any], frame_limit: int) -> list[float]:
    count = min(int(frame_limit), int(metadata["frame_count"]))
    if count < 2:
        raise ValueError("At least two sampled frames are required.")
    indices = np.linspace(0, int(metadata["frame_count"]) - 1, count)
    return [float(index / metadata["fps"]) for index in indices]


def calculate_ssim(image_a: np.ndarray, image_b: np.ndarray) -> float:
    x = cv2.cvtColor(image_a, cv2.COLOR_RGB2GRAY).astype(np.float64)
    y = cv2.cvtColor(image_b, cv2.COLOR_RGB2GRAY).astype(np.float64)
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    sigma = 1.5

    mu_x = cv2.GaussianBlur(x, (0, 0), sigma)
    mu_y = cv2.GaussianBlur(y, (0, 0), sigma)
    mu_x_sq = mu_x * mu_x
    mu_y_sq = mu_y * mu_y
    mu_xy = mu_x * mu_y

    sigma_x_sq = cv2.GaussianBlur(x * x, (0, 0), sigma) - mu_x_sq
    sigma_y_sq = cv2.GaussianBlur(y * y, (0, 0), sigma) - mu_y_sq
    sigma_xy = cv2.GaussianBlur(x * y, (0, 0), sigma) - mu_xy

    numerator = (2.0 * mu_xy + c1) * (2.0 * sigma_xy + c2)
    denominator = (mu_x_sq + mu_y_sq + c1) * (sigma_x_sq + sigma_y_sq + c2)
    return float(np.mean(numerator / denominator))


def calculate_psnr(image_a: np.ndarray, image_b: np.ndarray) -> float:
    mse = float(
        np.mean(
            (image_a.astype(np.float64) - image_b.astype(np.float64)) ** 2
        )
    )
    return float("inf") if mse == 0 else float(10.0 * np.log10(255.0**2 / mse))


def palette_w1(
    frame_rgb: np.ndarray,
    style_rgb: np.ndarray,
    channels: tuple[int, ...],
) -> float:
    frame_lab = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2LAB)
    style_lab = cv2.cvtColor(style_rgb, cv2.COLOR_RGB2LAB)
    distances = []
    for channel in channels:
        frame_values = frame_lab[:, :, channel].ravel()
        style_values = style_lab[:, :, channel].ravel()
        frame_hist = np.bincount(frame_values, minlength=256).astype(np.float64)
        style_hist = np.bincount(style_values, minlength=256).astype(np.float64)
        frame_hist /= max(frame_hist.sum(), 1.0)
        style_hist /= max(style_hist.sum(), 1.0)
        distances.append(
            float(np.abs(np.cumsum(frame_hist) - np.cumsum(style_hist)).sum())
            / 255.0
            * 100.0
        )
    return float(np.mean(distances))


def to_gray(frame_rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def farneback_flow(previous_gray: np.ndarray, next_gray: np.ndarray) -> np.ndarray:
    return cv2.calcOpticalFlowFarneback(
        previous_gray,
        next_gray,
        None,
        pyr_scale=0.5,
        levels=3,
        winsize=15,
        iterations=3,
        poly_n=5,
        poly_sigma=1.2,
        flags=0,
    )


def consistency_mask(
    previous_gray: np.ndarray,
    next_gray: np.ndarray,
    forward_flow: np.ndarray,
    threshold: float = 1.5,
) -> np.ndarray:
    backward_flow = farneback_flow(next_gray, previous_gray)
    back_at_forward = cv2.remap(
        backward_flow,
        forward_flow[:, :, 0],
        forward_flow[:, :, 1],
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0),
    )
    consistency_error = np.linalg.norm(forward_flow + back_at_forward, axis=2)
    return consistency_error < threshold


def pearson_flow_correlation(flow_a: np.ndarray, flow_b: np.ndarray) -> float:
    a = flow_a.reshape(-1, 2)
    b = flow_b.reshape(-1, 2)
    a = a - a.mean(axis=0, keepdims=True)
    b = b - b.mean(axis=0, keepdims=True)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 1e-12:
        return 0.0
    return float(np.sum(a * b) / denominator)


def temporal_metrics(
    source_frames: list[np.ndarray],
    output_frames: list[np.ndarray],
    offset: int,
) -> dict[str, float | None]:
    if len(source_frames) <= offset:
        return {
            "warp_rmse": None,
            "warp_mae": None,
            "flow_epe": None,
            "flow_correlation": None,
            "occlusion_ratio": None,
        }

    source_gray = [to_gray(frame) for frame in source_frames]
    output_gray = [to_gray(frame) for frame in output_frames]
    warp_rmse: list[float] = []
    warp_mae: list[float] = []
    epe_values: list[float] = []
    correlations: list[float] = []
    occlusion_ratios: list[float] = []

    for index in range(0, len(source_frames) - offset):
        next_index = index + offset
        source_flow = farneback_flow(
            source_gray[index], source_gray[next_index]
        )
        output_flow = farneback_flow(
            output_gray[index], output_gray[next_index]
        )
        valid = consistency_mask(
            source_gray[index], source_gray[next_index], source_flow
        )
        height, width = valid.shape
        margin = 8
        valid[:margin, :] = False
        valid[-margin:, :] = False
        valid[:, :margin] = False
        valid[:, -margin:] = False
        if not np.any(valid):
            continue

        warped_next = cv2.remap(
            output_frames[next_index],
            source_flow[:, :, 0],
            source_flow[:, :, 1],
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )
        difference = (
            warped_next.astype(np.float64)
            - output_frames[index].astype(np.float64)
        )
        pixel_error = np.mean(difference * difference, axis=2)
        warp_rmse.append(float(np.sqrt(np.mean(pixel_error[valid]))))
        warp_mae.append(
            float(np.mean(np.abs(difference[valid]).mean(axis=1)))
        )

        endpoint_error = np.linalg.norm(source_flow - output_flow, axis=2)
        epe_values.append(float(np.mean(endpoint_error[valid])))
        correlations.append(pearson_flow_correlation(source_flow[valid], output_flow[valid]))
        occlusion_ratios.append(float(1.0 - np.mean(valid)))

    return {
        "warp_rmse": mean_or_none(warp_rmse),
        "warp_mae": mean_or_none(warp_mae),
        "flow_epe": mean_or_none(epe_values),
        "flow_correlation": mean_or_none(correlations),
        "occlusion_ratio": mean_or_none(occlusion_ratios),
    }


def luminance_flicker(frames: list[np.ndarray]) -> float | None:
    if len(frames) < 3:
        return None
    means = np.array(
        [
            cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).mean(dtype=np.float64)
            for frame in frames
        ]
    )
    x = np.arange(len(means), dtype=np.float64)
    slope, intercept = np.polyfit(x, means, 1)
    residual = means - (slope * x + intercept)
    return float(np.sqrt(np.mean(residual * residual)))


def evaluate_method(
    source_frames: list[np.ndarray],
    style_image: np.ndarray,
    output_frames: list[np.ndarray],
    temporal_offsets: list[int],
) -> dict[str, Any]:
    ssim_values = [
        calculate_ssim(source, output)
        for source, output in zip(source_frames, output_frames)
    ]
    psnr_values = [
        calculate_psnr(source, output)
        for source, output in zip(source_frames, output_frames)
    ]
    palette_values = [
        palette_w1(output, style_image, (0, 1, 2)) for output in output_frames
    ]
    chroma_values = [
        palette_w1(output, style_image, (1, 2)) for output in output_frames
    ]
    metrics: dict[str, float | None] = {
        "ssim": float(np.mean(ssim_values)),
        "psnr": float(np.mean(psnr_values)),
        "lab_palette_w1": float(np.mean(palette_values)),
        "lab_ab_palette_w1": float(np.mean(chroma_values)),
        "luminance_flicker": luminance_flicker(output_frames),
    }
    for offset in temporal_offsets:
        values = temporal_metrics(source_frames, output_frames, offset)
        prefix = f"offset_{offset}_"
        metrics[f"{prefix}warp_rmse"] = values["warp_rmse"]
        metrics[f"{prefix}warp_mae"] = values["warp_mae"]
        metrics[f"{prefix}flow_epe"] = values["flow_epe"]
        metrics[f"{prefix}flow_correlation"] = values["flow_correlation"]
        metrics[f"{prefix}occlusion_ratio"] = values["occlusion_ratio"]
    return metrics


def dynamically_add_metric_info(metrics: dict[str, Any]) -> None:
    for key in metrics:
        if key in METRIC_INFO:
            continue
        if "_warp_rmse" in key or "_warp_mae" in key:
            METRIC_INFO[key] = {
                "label": key.replace("_", " ").upper(),
                "dimension": "temporal",
                "higher_is_better": False,
                "unit": "RGB levels",
            }
        elif "_flow_epe" in key:
            METRIC_INFO[key] = {
                "label": key.replace("_", " ").upper(),
                "dimension": "motion",
                "higher_is_better": False,
                "unit": "px",
            }
        elif "_flow_correlation" in key:
            METRIC_INFO[key] = {
                "label": key.replace("_", " ").upper(),
                "dimension": "motion",
                "higher_is_better": True,
                "unit": "",
            }
        elif "_occlusion_ratio" in key:
            METRIC_INFO[key] = {
                "label": key.replace("_", " ").upper(),
                "dimension": "diagnostic",
                "higher_is_better": False,
                "unit": "ratio",
            }


def bootstrap_mean_ci(
    values: list[float],
    seed: int,
    iterations: int = 2000,
) -> list[float] | None:
    if len(values) < 5:
        return None
    rng = random.Random(seed)
    array = np.asarray(values, dtype=np.float64)
    samples = [
        float(np.mean(array[[rng.randrange(len(array)) for _ in array]]))
        for _ in range(iterations)
    ]
    return [float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))]


def aggregate_results(
    cases: list[dict[str, Any]],
    method_order: list[str],
    seed: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    aggregates: dict[str, Any] = {}
    per_method_values: dict[str, dict[str, list[float]]] = {}
    for method_id in method_order:
        values: dict[str, list[float]] = {}
        for case in cases:
            result = case["methods"].get(method_id)
            if not result or not result.get("valid"):
                continue
            for metric, metric_value in result["metrics"].items():
                value = finite_float(metric_value)
                if value is not None:
                    values.setdefault(metric, []).append(value)
        per_method_values[method_id] = values
        summaries = {}
        for metric, metric_values in values.items():
            summaries[metric] = {
                "n": len(metric_values),
                "mean": float(np.mean(metric_values)),
                "std": float(np.std(metric_values, ddof=1))
                if len(metric_values) > 1
                else 0.0,
                "median": float(np.median(metric_values)),
                "min": float(np.min(metric_values)),
                "max": float(np.max(metric_values)),
                "ci95_mean": bootstrap_mean_ci(metric_values, seed),
            }
        aggregates[method_id] = summaries

    pairwise = []
    all_metrics = sorted(
        set().union(
            *(set(values) for values in per_method_values.values())
        )
    )
    for first_index, method_a in enumerate(method_order):
        for method_b in method_order[first_index + 1 :]:
            for metric in all_metrics:
                paired_values = []
                for case in cases:
                    result_a = case["methods"].get(method_a)
                    result_b = case["methods"].get(method_b)
                    if not result_a or not result_b:
                        continue
                    if not result_a.get("valid") or not result_b.get("valid"):
                        continue
                    value_a = finite_float(result_a["metrics"].get(metric))
                    value_b = finite_float(result_b["metrics"].get(metric))
                    if value_a is not None and value_b is not None:
                        paired_values.append(value_a - value_b)
                if not paired_values:
                    continue
                pairwise.append(
                    {
                        "method_a": method_a,
                        "method_b": method_b,
                        "metric": metric,
                        "n": len(paired_values),
                        "mean_diff_a_minus_b": float(np.mean(paired_values)),
                        "ci95_diff": bootstrap_mean_ci(
                            paired_values, seed + len(pairwise)
                        ),
                    }
                )
    return aggregates, pairwise


def fit_image_on_canvas(
    image: np.ndarray | Image.Image,
    width: int,
    height: int,
) -> Image.Image:
    pillow_image = (
        Image.fromarray(image) if isinstance(image, np.ndarray) else image.copy()
    ).convert("RGB")
    scale = min(width / pillow_image.width, height / pillow_image.height)
    resized = pillow_image.resize(
        (
            max(1, int(round(pillow_image.width * scale))),
            max(1, int(round(pillow_image.height * scale))),
        ),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGB", (width, height), (18, 21, 26))
    canvas.paste(
        resized,
        ((width - resized.width) // 2, (height - resized.height) // 2),
    )
    return canvas


def make_contact_sheet(
    case: dict[str, Any],
    style_image: np.ndarray,
    blind_map: dict[str, str],
    output_path: Path,
) -> None:
    source_frames = case["_source_frames"]
    column_count = min(5, len(source_frames))
    indices = np.linspace(0, len(source_frames) - 1, column_count).round().astype(int)
    cell_width = 230
    cell_height = 150
    left_margin = 116
    top_margin = 92
    label_height = 28
    row_gap = 16
    rows = 1 + len(blind_map)
    width = left_margin + column_count * cell_width + 24
    height = top_margin + rows * (cell_height + label_height + row_gap) + 28
    sheet = Image.new("RGB", (width, height), (13, 16, 21))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 17)
        small = ImageFont.truetype("arial.ttf", 13)
        heading = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
        small = ImageFont.load_default()
        heading = ImageFont.load_default()

    draw.text((116, 16), f"Case {case['id']}", fill=(238, 241, 247), font=heading)
    draw.text(
        (116, 50),
        "Blind review sheet - judge style, content and temporal evidence separately.",
        fill=(154, 165, 180),
        font=small,
    )

    style_thumb = fit_image_on_canvas(style_image, 78, 58)
    sheet.paste(style_thumb, (20, 22))
    draw.text((20, 4), "STYLE", fill=(154, 165, 180), font=small)
    draw.rectangle((20, 22, 98, 80), outline=(94, 108, 128), width=1)

    labels_and_frames: list[tuple[str, list[np.ndarray]]] = [
        ("SOURCE", source_frames),
    ]
    for blind_label, method_id in sorted(blind_map.items(), key=lambda item: item[0]):
        labels_and_frames.append(
            (blind_label, case["methods"][method_id]["_frames"])
        )

    for row_index, (label, frames) in enumerate(labels_and_frames):
        y = top_margin + row_index * (cell_height + label_height + row_gap)
        draw.text((18, y + 12), label, fill=(231, 235, 242), font=font)
        for column_index, frame_index in enumerate(indices):
            x = left_margin + column_index * cell_width
            framed = fit_image_on_canvas(frames[int(frame_index)], cell_width - 8, cell_height)
            sheet.paste(framed, (x, y))
            timestamp = case["sample_times_s"][int(frame_index)]
            draw.text(
                (x + 4, y + cell_height + 3),
                f"t={timestamp:.2f}s",
                fill=(142, 154, 171),
                font=small,
            )
            draw.rectangle(
                (x, y, x + cell_width - 8, y + cell_height),
                outline=(55, 64, 79),
                width=1,
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=92, subsampling=0)


def make_blind_map(
    case_id: str,
    method_ids: list[str],
    blind: bool,
    seed: int,
) -> dict[str, str]:
    ordered = method_ids.copy()
    if blind:
        random.Random(f"{seed}:{case_id}").shuffle(ordered)
    return {f"M{index + 1}": method_id for index, method_id in enumerate(ordered)}


def write_review_packet(
    cases: list[dict[str, Any]],
    blind_maps: dict[str, dict[str, str]],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet = {
        "schema_version": "1.0",
        "review_protocol": "references/vlm-rubric.md",
        "score_dimensions": SCORE_DIMENSIONS,
        "cases": [
            {
                "case_id": case["id"],
                "style_id": case.get("style_id"),
                "content_id": case.get("content_id"),
                "contact_sheet": case.get("contact_sheet"),
                "method_blind_ids": sorted(blind_maps[case["id"]]),
            }
            for case in cases
        ],
    }
    (output_dir / "packet.json").write_text(
        json.dumps(packet, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "blind_map.json").write_text(
        json.dumps(blind_maps, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    template = {
        "schema_version": "1.0",
        "reviewer": {
            "id": "reviewer-1",
            "type": "vlm",
            "model": "replace-with-model-version",
            "review_date": "YYYY-MM-DD",
            "blind": True,
            "input_scope": "contact_sheets_only",
        },
        "scores": [
            {
                "case_id": case["id"],
                "method_blind_id": blind_id,
                "insufficient": None,
                **{dimension: None for dimension in SCORE_DIMENSIONS},
                "confidence": None,
                "failure_tags": [],
                "evidence": "",
                "comments": "",
            }
            for case in cases
            for blind_id in sorted(blind_maps[case["id"]])
        ],
        "preferences": [],
    }
    (output_dir / "completed_review_template.json").write_text(
        json.dumps(template, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_dir = manifest_path.parent
    experiment = manifest.get("experiment", {})
    frame_limit = int(experiment.get("frame_limit", 48))
    max_side = int(experiment.get("max_side", 384))
    temporal_offsets = sorted(
        {
            int(value)
            for value in experiment.get("temporal_offsets", [1, 5])
            if int(value) > 0
        }
    )
    if not temporal_offsets:
        temporal_offsets = [1]

    methods = manifest.get("methods", [])
    method_order = [method["id"] for method in methods]
    if len(method_order) != len(set(method_order)):
        raise ValueError("Method IDs must be unique.")
    if not method_order:
        raise ValueError("Manifest must define at least one method.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    contact_dir = args.output_dir / "contact_sheets"
    cases_out: list[dict[str, Any]] = []
    blind_maps: dict[str, dict[str, str]] = {}

    for case in manifest.get("cases", []):
        case_id = str(case["id"])
        source_path = resolve_path(case["source_video"], manifest_dir)
        style_path = resolve_path(case["style_image"], manifest_dir)
        warnings: list[str] = []
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        if not style_path.exists():
            raise FileNotFoundError(style_path)
        source_metadata = read_video_metadata(source_path)
        times = sample_times(source_metadata, frame_limit)
        source_frames = read_frames_at_times(source_path, times, max_side)
        target_wh = (source_frames[0].shape[1], source_frames[0].shape[0])
        style_bgr = cv2.imread(str(style_path), cv2.IMREAD_COLOR)
        if style_bgr is None:
            raise ValueError(f"Cannot decode style image: {style_path}")
        style_image = resize_rgb(cv2.cvtColor(style_bgr, cv2.COLOR_BGR2RGB), max_side)

        case_out: dict[str, Any] = {
            "id": case_id,
            "content_id": case.get("content_id"),
            "style_id": case.get("style_id"),
            "split": case.get("split", experiment.get("split", "unspecified")),
            "source_video": str(source_path),
            "source_sha256": sha256_file(source_path),
            "source_metadata": source_metadata,
            "style_image": str(style_path),
            "style_sha256": sha256_file(style_path),
            "sample_times_s": times,
            "methods": {},
            "warnings": warnings,
            "_source_frames": source_frames,
        }

        outputs = case.get("outputs", {})
        present_methods = [method_id for method_id in method_order if method_id in outputs]
        if not present_methods:
            raise ValueError(f"Case {case_id} has no outputs for known methods.")
        missing_methods = sorted(set(method_order) - set(present_methods))
        if missing_methods:
            warnings.append(f"Missing methods: {', '.join(missing_methods)}")

        for method_id in present_methods:
            output_config = outputs[method_id]
            output_path = resolve_path(output_config["video"], manifest_dir)
            method_result: dict[str, Any] = {
                "valid": False,
                "method_id": method_id,
                "video": str(output_path),
            }
            case_out["methods"][method_id] = method_result
            if not output_path.exists():
                method_result["error"] = "Output video not found."
                continue
            try:
                output_metadata = read_video_metadata(output_path)
            except ValueError as error:
                method_result["error"] = str(error)
                continue
            method_result["output_metadata"] = output_metadata
            method_result["video_sha256"] = sha256_file(output_path)
            duration_delta = abs(
                output_metadata["duration_s"] - source_metadata["duration_s"]
            )
            duration_tolerance = max(
                0.15, 2.5 / source_metadata["fps"]
            )
            if duration_delta > duration_tolerance:
                method_result["error"] = (
                    f"Duration mismatch: output {output_metadata['duration_s']:.3f}s, "
                    f"source {source_metadata['duration_s']:.3f}s."
                )
                continue
            aspect_delta = abs(
                output_metadata["aspect_ratio"] - source_metadata["aspect_ratio"]
            ) / source_metadata["aspect_ratio"]
            if aspect_delta > 0.02:
                method_result["error"] = (
                    f"Aspect-ratio mismatch: output {output_metadata['aspect_ratio']:.4f}, "
                    f"source {source_metadata['aspect_ratio']:.4f}."
                )
                continue
            try:
                output_frames = read_frames_at_times(
                    output_path, times, max_side, target_wh=target_wh
                )
                metrics = evaluate_method(
                    source_frames, style_image, output_frames, temporal_offsets
                )
            except (ValueError, cv2.error) as error:
                method_result["error"] = f"Metric evaluation failed: {error}"
                continue
            metrics["runtime_s"] = finite_float(output_config.get("runtime_s"))
            metrics["peak_memory_gb"] = finite_float(
                output_config.get("peak_memory_gb")
            )
            method_result.update(
                {
                    "valid": True,
                    "metrics": metrics,
                    "_frames": output_frames,
                }
            )
            dynamically_add_metric_info(metrics)

        valid_methods = [
            method_id
            for method_id, result in case_out["methods"].items()
            if result.get("valid")
        ]
        blind_maps[case_id] = make_blind_map(
            case_id, valid_methods, args.blind, args.seed
        )
        if not args.no_contact_sheets and valid_methods:
            contact_path = contact_dir / f"{case_id}.jpg"
            make_contact_sheet(
                case_out,
                style_image,
                blind_maps[case_id],
                contact_path,
            )
            case_out["contact_sheet"] = str(contact_path.resolve())
        cases_out.append(case_out)

    aggregates, pairwise = aggregate_results(cases_out, method_order, args.seed)
    write_review_packet(cases_out, blind_maps, args.output_dir / "review_packet")

    serializable_cases = []
    for case in cases_out:
        copied_case = {
            key: value for key, value in case.items() if not key.startswith("_")
        }
        copied_methods = {}
        for method_id, method_result in copied_case["methods"].items():
            copied_methods[method_id] = {
                key: value
                for key, value in method_result.items()
                if not key.startswith("_")
            }
        copied_case["methods"] = copied_methods
        serializable_cases.append(copied_case)

    result = {
        "schema_version": "1.0",
        "generated_by": "video-style-transfer-eval/evaluate.py",
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "experiment": {
            **experiment,
            "frame_limit": frame_limit,
            "max_side": max_side,
            "temporal_offsets": temporal_offsets,
            "blind": args.blind,
            "blind_seed": args.seed,
            "flow_implementation": "OpenCV Farneback (diagnostic proxy)",
        },
        "methods": manifest.get("methods", []),
        "metric_info": METRIC_INFO,
        "review_dimensions": SCORE_DIMENSIONS,
        "cases": serializable_cases,
        "aggregates": aggregates,
        "pairwise": pairwise,
        "review_packet": str(
            (args.output_dir / "review_packet" / "packet.json").resolve()
        ),
        "blind_map": str(
            (args.output_dir / "review_packet" / "blind_map.json").resolve()
        ),
    }
    metrics_path = args.output_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {metrics_path}")
    print(f"Wrote {args.output_dir / 'review_packet'}")


if __name__ == "__main__":
    main()
