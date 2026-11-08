#!/usr/bin/env python3
"""Render a validated VST evaluation as Markdown, standalone HTML, and PDF."""

from __future__ import annotations

import argparse
import copy
import html
import json
import math
import os
import shutil
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


KEY_METRICS = [
    ("artfid", "ArtFID"),
    ("fid", "FID"),
    ("clip_i", "CLIP-I"),
    ("ssim", "SSIM"),
    ("psnr", "PSNR"),
    ("lpips", "LPIPS"),
    ("clip_f", "CLIP-F"),
    ("lab_palette_w1", "LAB palette W1"),
    ("lab_ab_palette_w1", "LAB chroma W1"),
    ("offset_1_warp_rmse", "Warp RMSE, offset 1"),
    ("offset_5_warp_rmse", "Warp RMSE, offset 5"),
    ("offset_1_flow_epe", "Flow EPE, offset 1"),
    ("offset_1_flow_correlation", "Flow correlation, offset 1"),
    ("tlp", "tLP"),
    ("clip_cons", "CLIP-CONS"),
    ("luminance_flicker", "Luminance flicker"),
    ("runtime_s", "Runtime"),
    ("peak_memory_gb", "Peak GPU memory"),
]
REVIEW_DIMENSIONS = [
    "style_adherence",
    "content_preservation",
    "temporal_stability",
    "artifact_control",
    "overall_visual_quality",
]

STATUS_CODES = ("Exploratory", "Provisional", "Comparative", "Paper-ready")

STATUS_ZH = {
    "Exploratory": "探索性",
    "Provisional": "初步",
    "Comparative": "对比性",
    "Paper-ready": "可发表级",
}

DIMENSION_LABELS = {
    "en": {
        "style_adherence": "Style adherence",
        "content_preservation": "Content preservation",
        "temporal_stability": "Temporal stability",
        "artifact_control": "Artifact control",
        "overall_visual_quality": "Overall visual quality",
    },
    "zh": {
        "style_adherence": "风格一致性",
        "content_preservation": "内容保持",
        "temporal_stability": "时序稳定性",
        "artifact_control": "伪影控制",
        "overall_visual_quality": "整体视觉质量",
    },
}

FAILURE_LABELS = {
    "en": {tag: tag.replace("_", " ") for tag in (
        "flicker",
        "texture_sticking",
        "texture_drift",
        "identity_drift",
        "geometry_melting",
        "edge_ghosting",
        "occlusion_break",
        "new_region_error",
        "motion_duplication",
        "temporal_jump",
        "color_bleed",
        "banding",
        "detail_loss",
        "reference_copied",
    )},
    "zh": {
        "flicker": "闪烁",
        "texture_sticking": "纹理附着/粘连",
        "texture_drift": "纹理漂移",
        "identity_drift": "身份漂移",
        "geometry_melting": "几何融化",
        "edge_ghosting": "边缘重影",
        "occlusion_break": "遮挡关系错误",
        "new_region_error": "新区域错误",
        "motion_duplication": "运动复制",
        "temporal_jump": "时序跳变",
        "color_bleed": "颜色渗漏",
        "banding": "色带",
        "detail_loss": "细节损失",
        "reference_copied": "复制参考构图",
    },
}

METRIC_LABELS_ZH = {
    "ssim": "SSIM 结构相似度",
    "psnr": "PSNR 峰值信噪比",
    "lab_palette_w1": "LAB 调色板 W1",
    "lab_ab_palette_w1": "LAB 色度 W1",
    "luminance_flicker": "亮度闪烁",
    "runtime_s": "运行时间",
    "peak_memory_gb": "峰值 GPU 显存",
    "offset_1_warp_rmse": "重映射 RMSE Δ1",
    "offset_5_warp_rmse": "重映射 RMSE Δ5",
    "offset_1_flow_epe": "光流端点误差 Δ1",
    "offset_1_flow_correlation": "光流相关性 Δ1",
    "tlp": "tLP 时序感知误差",
    "clip_cons": "CLIP-CONS 时序一致性",
    "lpips": "LPIPS 感知距离",
    "clip_i": "CLIP-I 图像风格相似度",
    "clip_f": "CLIP-F 图像内容相似度",
    "fid": "FID 分布距离",
    "artfid": "ArtFID",
}

TEXT = {
    "en": {
        "default_title": "Video Style Transfer Evaluation",
        "default_claim": "Compare video style transfer quality while keeping style, content, motion, and temporal evidence separate.",
        "claim": "Claim",
        "claim_status": "Claim status",
        "date": "Date",
        "executive": "Executive verdict",
        "protocol": "Protocol and reproducibility",
        "evidence_gates": "Evidence gates",
        "gate": "Gate",
        "value": "Value",
        "status": "Status",
        "flow_implementation": "Flow implementation",
        "manifest_sha": "Manifest SHA-256",
        "sample_frames": "Sampled frames per video",
        "max_side": "Maximum evaluation side",
        "temporal_offsets": "Temporal offsets",
        "blinding": "Blinding",
        "dataset": "Dataset and pairing",
        "case": "Case",
        "content": "Content",
        "style": "Style",
        "split": "Split",
        "valid_methods": "Valid methods",
        "warnings": "Warnings",
        "none": "None",
        "quantitative": "Quantitative results",
        "style_heading": "Style",
        "content_heading": "Content",
        "temporal_heading": "Temporal and motion",
        "cost_heading": "Cost",
        "method": "Method",
        "metrics_note": "Arrows indicate preferred direction. Values are macro mean ± sample standard deviation across valid clips; the clip is the statistical unit. OpenCV Farneback values are diagnostic proxies, not RAFT-comparable results.",
        "diagnostic_caveat": "Farneback flow and LAB palette distance are diagnostic proxies. They are not RAFT, LPIPS, CLIP, FID, or ArtFID.",
        "blind_review": "Blinded visual review",
        "artifacts": "Artifacts",
        "overall": "Overall",
        "failure_tags": "Failure tags",
        "no_failure_tags": "No failure tags were recorded in the reviewed sample.",
        "reviewer_records": "Reviewer records",
        "scored_records": "Scored case/method records",
        "vlm_caveat": "VLM scores are perceptual evidence, not ground truth.",
        "no_review": "No validated blinded VLM review is present. Visual claims remain pending.",
        "per_case": "Per-case outcomes",
        "invalid": "invalid",
        "contact_sheet": "Contact sheet for",
        "ablation": "Ablations and trade-offs",
        "ablation_text": "This report compares observed configurations only. A style-preservation frontier is not established unless the manifest contains a controlled style-strength sweep at fixed content, motion, and seed settings.",
        "failure_gallery": "Failure gallery",
        "failure_text": "The contact sheets above are the visual evidence packet. Failures should be read together with reviewer evidence and timestamps; attractive stills are not sufficient evidence of temporal quality.",
        "threats": "Threats to validity",
        "threats_list": [
            "Content and style distributions may not represent the intended use.",
            "Low-level metrics are sensitive to colorization and compression.",
            "Farneback flow is not RAFT and can fail on large motion or occlusions.",
            "A single style image does not define a valid FID style distribution.",
            "VLM review can have position, content, and prompt bias.",
            "External baseline numbers copied from papers may not use the same settings.",
            "Fewer than five clips do not support a stable comparative confidence interval.",
        ],
        "conclusion": "Conclusion and recommendation",
        "recommendation": "Recommendation",
        "generated": "Generated by video-style-transfer-eval. The accompanying Markdown and metrics JSON retain the machine-readable evidence trail.",
        "page": "Page",
        "footer": "Video Style Transfer Evaluation",
        "pending": "No validated blinded VLM review is present.",
        "per_case_note": "Each contact sheet contains a style thumbnail, source frames, and blinded candidates.",
        "review_table_headers": ["Method", "Style", "Content", "Temporal", "Artifacts", "Overall"],
        "per_case_headers": ["Method", "SSIM ↑", "Palette W1 ↓", "Warp RMSE Δ1 ↓", "Flow EPE Δ1 ↓"],
        "higher": "higher",
        "lower": "lower",
    },
    "zh": {
        "default_title": "视频风格迁移评估",
        "default_claim": "分别评估风格、内容、运动与时序证据，并给出可复现的视频风格迁移比较。",
        "claim": "评估目标",
        "claim_status": "结论状态",
        "date": "日期",
        "executive": "执行摘要",
        "protocol": "评估协议与可复现性",
        "evidence_gates": "证据完整性检查",
        "gate": "检查项",
        "value": "结果",
        "status": "状态",
        "flow_implementation": "光流实现",
        "manifest_sha": "清单 SHA-256",
        "sample_frames": "每个视频采样帧数",
        "max_side": "最大评估边长",
        "temporal_offsets": "时序偏移",
        "blinding": "盲评",
        "dataset": "数据集与配对设置",
        "case": "案例",
        "content": "内容",
        "style": "风格",
        "split": "数据划分",
        "valid_methods": "有效方法",
        "warnings": "警告",
        "none": "无",
        "quantitative": "定量结果",
        "style_heading": "风格迁移",
        "content_heading": "内容保持",
        "temporal_heading": "时序与运动",
        "cost_heading": "计算成本",
        "method": "方法",
        "metrics_note": "箭头表示指标偏好方向。数值为有效片段上的宏平均 ± 样本标准差，统计单位为片段。OpenCV Farneback 是诊断代理，不能与 RAFT 论文数值直接比较。",
        "diagnostic_caveat": "Farneback 光流与 LAB 调色板距离是诊断代理，不能替代 RAFT、LPIPS、CLIP、FID 或 ArtFID。",
        "blind_review": "盲评视觉审查",
        "artifacts": "伪影",
        "overall": "整体",
        "failure_tags": "失败标签",
        "no_failure_tags": "本次审查样本未记录失败标签。",
        "reviewer_records": "审查记录数",
        "scored_records": "已评分案例/方法记录",
        "vlm_caveat": "VLM 评分是感知证据，不是真实标签。",
        "no_review": "当前没有经过校验的盲评 VLM 记录，视觉结论仍待补充。",
        "per_case": "单案例结果",
        "invalid": "无效",
        "contact_sheet": "案例联系表",
        "ablation": "消融实验与权衡",
        "ablation_text": "本报告只比较已观察到的配置。除非在固定内容、运动和随机种子的条件下完成受控的风格强度扫描，否则不能声称已建立风格-保持前沿。",
        "failure_gallery": "失败案例分析",
        "failure_text": "上方联系表构成视觉证据包。失败判断应结合审查证据和时间点；仅有吸引力较高的静态帧不足以证明时序质量。",
        "threats": "有效性威胁",
        "threats_list": [
            "内容与风格的数据分布可能不能代表实际使用场景。",
            "低层指标容易受全局着色和压缩影响。",
            "Farneback 光流不是 RAFT，在大运动或遮挡条件下可能失效。",
            "单张风格图不能构成有效的 FID 风格分布。",
            "VLM 审查可能受到位置、内容和提示词偏差影响。",
            "直接引用论文的外部基线数值可能没有统一推理设置。",
            "少于五个片段时，比较置信区间不稳定。",
        ],
        "conclusion": "结论与建议",
        "recommendation": "下一步建议",
        "generated": "由 video-style-transfer-eval 生成。配套 Markdown 和指标 JSON 保存机器可读的证据链。",
        "page": "第",
        "footer": "视频风格迁移评估",
        "pending": "当前没有经过校验的盲评 VLM 记录。",
        "per_case_note": "每个联系表包含风格缩略图、源视频帧和盲化候选结果。",
        "review_table_headers": ["方法", "风格", "内容", "时序", "伪影", "整体"],
        "per_case_headers": ["方法", "SSIM 越高越好", "调色板 W1 越低越好", "重映射 RMSE Δ1 越低越好", "光流 EPE Δ1 越低越好"],
        "higher": "越高越好",
        "lower": "越低越好",
    },
}


def tr(lang: str, key: str) -> Any:
    return TEXT[lang][key]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument(
        "--review",
        type=Path,
        help="Validated review export. Omit when visual review is unavailable.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--language", choices=["en", "zh", "both"], default="both")
    parser.add_argument("--title", help="English report title.")
    parser.add_argument("--title-zh", help="Chinese report title.")
    parser.add_argument("--claim", help="English report claim.")
    parser.add_argument("--claim-zh", help="Chinese report claim.")
    parser.add_argument("--primary", help="Primary method ID for summary sentences.")
    parser.add_argument("--baseline", help="Baseline method ID for paired comparisons.")
    parser.add_argument(
        "--status",
        choices=STATUS_CODES,
        help="Override the automatically inferred claim status.",
    )
    parser.add_argument(
        "--cjk-font",
        type=Path,
        help="Regular CJK TTF/OTF/TTC for Chinese PDF. Auto-detects a system font when omitted.",
    )
    parser.add_argument(
        "--cjk-font-bold",
        type=Path,
        help="Bold CJK TTF/OTF/TTC. Defaults to the regular font.",
    )
    parser.add_argument("--report-date", default=date.today().isoformat())
    return parser.parse_args()


def format_number(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return str(number)
    if abs(number) >= 1000:
        return f"{number:,.1f}"
    if abs(number) >= 100:
        return f"{number:.1f}"
    if abs(number) >= 10:
        return f"{number:.2f}"
    return f"{number:.{digits}f}"


def format_stat(summary: dict[str, Any] | None, digits: int = 4) -> str:
    if not summary:
        return "n/a"
    mean = format_number(summary.get("mean"), digits)
    std = format_number(summary.get("std"), digits)
    n = summary.get("n", 0)
    return f"{mean} ± {std} (n={n})"


def direction_symbol(metric: str, metric_info: dict[str, Any]) -> str:
    return "↑" if metric_info.get(metric, {}).get("higher_is_better") else "↓"


def metric_label(lang: str, metric: str, info: dict[str, Any]) -> str:
    if lang == "zh":
        return METRIC_LABELS_ZH.get(metric, info.get("label", metric))
    return info.get("label", metric)


def method_maps(
    metrics: dict[str, Any],
    lang: str = "en",
) -> tuple[dict[str, str], dict[str, str]]:
    labels = {}
    colors_by_method = {}
    palette = ["#1D5C63", "#D27A36", "#5B6BBF", "#A23B72", "#2F8F63", "#7A5C3E"]
    for index, method in enumerate(metrics.get("methods", [])):
        method_id = method["id"]
        labels[method_id] = (
            method.get("label_zh")
            if lang == "zh" and method.get("label_zh")
            else method.get("label", method_id)
        )
        colors_by_method[method_id] = palette[index % len(palette)]
    return labels, colors_by_method


def infer_status(metrics: dict[str, Any], review: dict[str, Any] | None) -> str:
    experiment = metrics.get("experiment", {})
    split = str(experiment.get("split", "unspecified")).lower()
    valid_cases = sum(
        1
        for case in metrics.get("cases", [])
        if any(result.get("valid") for result in case.get("methods", {}).values())
    )
    reviews = review.get("reviews", []) if review else []
    if "demo" in split or "synthetic" in split or valid_cases < 2:
        return "Exploratory"
    if not reviews:
        return "Provisional"
    if valid_cases >= 2:
        return "Comparative"
    return "Provisional"


def load_review(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("reviews"), list):
        raise ValueError(
            "Review input must be the validated export containing a 'reviews' list."
        )
    return data


def aggregate_reviews(
    review: dict[str, Any] | None,
    labels: dict[str, str],
) -> dict[str, Any]:
    if not review:
        return {
            "reviewer_count": 0,
            "scored_count": 0,
            "method_dimension": {},
            "failure_counts": Counter(),
            "preference_counts": {},
            "per_case": {},
        }

    per_reviewer_method_dimension: dict[
        tuple[str, str, str], list[int]
    ] = defaultdict(list)
    per_case: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    failure_counts: Counter[str] = Counter()
    preference_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    scored_count = 0

    for item in review.get("reviews", []):
        reviewer_id = item.get("reviewer", {}).get("id", "unknown")
        for score in item.get("scores", []):
            if score.get("insufficient") is True:
                continue
            method_id = score.get("method_id")
            if not method_id:
                continue
            case_id = score.get("case_id")
            scored_count += 1
            per_case[(case_id, method_id)].append(score)
            for dimension in REVIEW_DIMENSIONS:
                value = score.get(dimension)
                if isinstance(value, int) and 1 <= value <= 5:
                    per_reviewer_method_dimension[
                        (reviewer_id, method_id, dimension)
                    ].append(value)
            failure_counts.update(score.get("failure_tags", []))

        for preference in item.get("preferences", []):
            if preference.get("tie") is True:
                winner = "tie"
            else:
                winner = preference.get("winner_method_id")
            if not winner:
                continue
            dimension = preference.get("dimension")
            if dimension not in REVIEW_DIMENSIONS:
                continue
            preference_counts[(dimension, winner)] += 1

    by_reviewer_method_dimension: dict[
        tuple[str, str], list[float]
    ] = defaultdict(list)
    for (reviewer_id, method_id, dimension), values in (
        per_reviewer_method_dimension.items()
    ):
        by_reviewer_method_dimension[(method_id, dimension)].append(float(np.mean(values)))

    method_dimension = {}
    for method_id in labels:
        method_dimension[method_id] = {}
        for dimension in REVIEW_DIMENSIONS:
            values = by_reviewer_method_dimension.get((method_id, dimension), [])
            method_dimension[method_id][dimension] = {
                "mean": float(np.mean(values)) if values else None,
                "std_across_reviewers": (
                    float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
                ),
                "reviewer_n": len(values),
            }

    return {
        "reviewer_count": review.get("reviewer_count", len(review.get("reviews", []))),
        "scored_count": scored_count,
        "method_dimension": method_dimension,
        "failure_counts": failure_counts,
        "preference_counts": preference_counts,
        "per_case": dict(per_case),
    }


def get_pairwise(
    metrics: dict[str, Any],
    method_a: str,
    method_b: str,
    metric: str,
) -> dict[str, Any] | None:
    for row in metrics.get("pairwise", []):
        if (
            row.get("method_a") == method_a
            and row.get("method_b") == method_b
            and row.get("metric") == metric
        ):
            return row
        if (
            row.get("method_a") == method_b
            and row.get("method_b") == method_a
            and row.get("metric") == metric
        ):
            copied = dict(row)
            copied["method_a"] = method_a
            copied["method_b"] = method_b
            copied["mean_diff_a_minus_b"] = -float(
                row.get("mean_diff_a_minus_b", 0.0)
            )
            if row.get("ci95_diff"):
                copied["ci95_diff"] = [
                    -float(row["ci95_diff"][1]),
                    -float(row["ci95_diff"][0]),
                ]
            return copied
    return None


def comparison_phrase(
    metrics: dict[str, Any],
    labels: dict[str, str],
    primary: str,
    baseline: str,
    metric: str,
    lang: str = "en",
) -> str:
    info = metrics.get("metric_info", {}).get(metric, {})
    primary_summary = (
        metrics.get("aggregates", {}).get(primary, {}).get(metric)
    )
    baseline_summary = (
        metrics.get("aggregates", {}).get(baseline, {}).get(metric)
    )
    if not primary_summary or not baseline_summary:
        name = metric_label(lang, metric, info)
        return (
            f"{name}：配对数据不足。"
            if lang == "zh"
            else f"{name}: insufficient paired data."
        )
    higher = bool(info.get("higher_is_better"))
    difference = float(primary_summary["mean"]) - float(baseline_summary["mean"])
    advantage = difference > 0 if higher else difference < 0
    relation = "更优" if advantage else "较差"
    if abs(difference) < 1e-12:
        relation = "持平"
    if lang == "en":
        relation = "better" if advantage else "worse"
        if abs(difference) < 1e-12:
            relation = "equal"
    symbol = "↑" if higher else "↓"
    paired = get_pairwise(metrics, primary, baseline, metric)
    ci_text = ""
    if paired and paired.get("ci95_diff") and paired.get("n", 0) >= 5:
        low, high = paired["ci95_diff"]
        ci_text = (
            f"；配对差值 95% CI [{format_number(low)}, {format_number(high)}]"
            if lang == "zh"
            else f"; paired difference 95% CI [{format_number(low)}, {format_number(high)}]"
        )
    name = metric_label(lang, metric, info)
    separator = "：" if lang == "zh" else ": "
    if lang == "zh":
        return (
            f"{name} {symbol}{separator}"
            f"{labels.get(primary, primary)} "
            f"{format_number(primary_summary['mean'])} 对 "
            f"{labels.get(baseline, baseline)} "
            f"{format_number(baseline_summary['mean'])}"
            f"（{relation}{ci_text}；n={primary_summary.get('n', 0)}）。"
        )
    return (
        f"{name} {symbol}{separator}"
        f"{labels.get(primary, primary)} "
        f"{format_number(primary_summary['mean'])} vs "
        f"{labels.get(baseline, baseline)} "
        f"{format_number(baseline_summary['mean'])} "
        f"({relation}{ci_text}; n={primary_summary.get('n', 0)})."
    )


def make_findings(
    metrics: dict[str, Any],
    labels: dict[str, str],
    review_agg: dict[str, Any],
    primary: str | None,
    baseline: str | None,
    lang: str = "en",
) -> list[str]:
    findings = []
    if primary and baseline and primary in labels and baseline in labels:
        for metric in [
            "ssim",
            "lab_palette_w1",
            "offset_1_warp_rmse",
            "offset_1_flow_epe",
            "runtime_s",
        ]:
            if metric in metrics.get("metric_info", {}):
                findings.append(
                    comparison_phrase(
                        metrics, labels, primary, baseline, metric, lang
                    )
                )
    if review_agg["scored_count"]:
        best_method = None
        best_score = -1.0
        for method_id, dimensions in review_agg["method_dimension"].items():
            value = dimensions["overall_visual_quality"]["mean"]
            if value is not None and value > best_score:
                best_method = method_id
                best_score = value
        if best_method:
            if lang == "zh":
                findings.append(
                    f"盲评 VLM 审查：{labels.get(best_method, best_method)}的整体视觉质量"
                    f"均值最高（{best_score:.2f}/5，"
                    f"{review_agg['reviewer_count']} 位审查者）；这是感知证据，不是基准真值。"
                )
            else:
                findings.append(
                    f"Blinded VLM review: {labels.get(best_method, best_method)} has "
                    f"the highest mean overall visual quality "
                    f"({best_score:.2f}/5 across "
                    f"{review_agg['reviewer_count']} reviewer(s)); this is perceptual evidence, "
                    "not benchmark ground truth."
                )
        if review_agg["failure_counts"]:
            tag, count = review_agg["failure_counts"].most_common(1)[0]
            if lang == "zh":
                findings.append(
                    f"最常见的视觉失败标签：{FAILURE_LABELS['zh'].get(tag, tag)}"
                    f"（{count} 次）。"
                )
            else:
                findings.append(
                    f"Most frequent visual failure tag: {tag.replace('_', ' ')} "
                    f"({count} occurrence(s))."
                )
    else:
        findings.append(
            "当前没有盲评 VLM 记录，因此不给出感知质量结论。"
            if lang == "zh"
            else "Blinded VLM review is absent, so no perceptual quality conclusion is made."
        )
    findings.append(
        "诊断性风格指标只衡量调色板对齐；纹理和笔触结论需要额外的感知证据。"
        if lang == "zh"
        else "The diagnostic style metric measures palette alignment only; texture and "
        "brushwork claims require perceptual evidence."
    )
    return findings


def evidence_rows(
    metrics: dict[str, Any],
    review_agg: dict[str, Any],
    status: str,
    lang: str = "en",
) -> list[tuple[str, str, str]]:
    cases = metrics.get("cases", [])
    valid_cases = sum(
        1
        for case in cases
        if any(result.get("valid") for result in case.get("methods", {}).values())
    )
    method_count = len(metrics.get("methods", []))
    reviews = review_agg["reviewer_count"]
    required_vlm = "已提供" if reviews else "缺失"
    paper_metrics = "未检测到"
    for method_aggregate in metrics.get("aggregates", {}).values():
        if any(metric in method_aggregate for metric in ("lpips", "clip_i", "clip_f", "fid", "artfid")):
            paper_metrics = "部分提供"
            break
    if lang == "en":
        required_vlm = "Present" if reviews else "Missing"
        paper_metrics = "Partially present" if paper_metrics == "部分提供" else "Not detected"
        items = [
            (
                "Paired valid cases",
                str(valid_cases),
                "Pass" if valid_cases >= 2 else "Limited",
            ),
            (
                "Methods",
                str(method_count),
                "Pass" if method_count >= 2 else "Single method",
            ),
            ("Blinded VLM review", required_vlm, "Pass" if reviews else "Incomplete"),
            (
                "Paper-grade perceptual metrics",
                paper_metrics,
                "Pass" if paper_metrics == "Partially present" else "Not established",
            ),
            (
                "Claim status",
                status,
                "Pass" if status in {"Comparative", "Paper-ready"} else "Caveat",
            ),
        ]
        return items
    return [
        (
            "有效配对案例",
            str(valid_cases),
            "通过" if valid_cases >= 2 else "有限",
        ),
        (
            "方法数量",
            str(method_count),
            "通过" if method_count >= 2 else "单一方法",
        ),
        ("盲评 VLM 记录", required_vlm, "通过" if reviews else "不完整"),
        (
            "论文级感知指标",
            paper_metrics,
            "通过" if paper_metrics == "部分提供" else "尚未建立",
        ),
        (
            "结论状态",
            STATUS_ZH[status],
            "通过" if status in {"Comparative", "Paper-ready"} else "需说明限制",
        ),
    ]


def decide_recommendation(
    metrics: dict[str, Any],
    labels: dict[str, str],
    review_agg: dict[str, Any],
    primary: str | None,
    baseline: str | None,
    status: str,
    lang: str = "en",
) -> str:
    if lang == "zh":
        if status == "Exploratory":
            return (
                "请使用当前结果验证评估流程并设计下一组实验。"
                "不要把这个合成演示作为模型性能证据。"
            )
        primary_name = labels.get(primary or "", primary or "主方法")
        if review_agg["failure_counts"]:
            top_tag = review_agg["failure_counts"].most_common(1)[0][0]
            return (
                f"在形成最终结论前，需要在更多留出配对样本上检查"
                f"“{FAILURE_LABELS['zh'].get(top_tag, top_tag)}”，"
                f"并报告 {primary_name} 在同等风格强度下的风格-保持前沿。"
            )
        if primary and baseline:
            return (
                f"继续扩大 {primary_name} 的留出配对研究，补充固定实现的 "
                "LPIPS/CLIP/RAFT 指标，并报告单案例不确定度，而不是只报告单一总排名。"
            )
        return "在做出比较性结论前，请补充配对基线和盲评视觉审查。"
    if status == "Exploratory":
        return (
            "Use these results to validate the evaluation pipeline and choose the "
            "next experiment. Do not treat the synthetic run as model evidence."
        )
    primary_name = labels.get(primary or "", primary or "the primary method")
    if review_agg["failure_counts"]:
        top_tag = review_agg["failure_counts"].most_common(1)[0][0]
        return (
            f"Before a final claim, inspect {top_tag.replace('_', ' ')} on additional "
            f"held-out pairs and report the {primary_name} style-preservation frontier "
            "at matched style strength."
        )
    if primary and baseline:
        return (
            f"Continue with a larger held-out paired study for {primary_name}, add "
            "fixed LPIPS/CLIP/RAFT implementations where needed, and report per-case "
            "uncertainty rather than a single aggregate rank."
        )
    return (
        "Add a paired baseline and blinded visual review before making a comparative claim."
    )


def metric_tables(
    metrics: dict[str, Any],
    labels: dict[str, str],
    lang: str = "en",
) -> list[dict[str, Any]]:
    dimensions = (
        [
            ("风格迁移", "style"),
            ("内容保持", "content"),
            ("时序与运动", "temporal"),
            ("计算成本", "cost"),
        ]
        if lang == "zh"
        else [
            ("Style", "style"),
            ("Content", "content"),
            ("Temporal and motion", "temporal"),
            ("Cost", "cost"),
        ]
    )
    info_by_metric = metrics.get("metric_info", {})
    method_order = [method["id"] for method in metrics.get("methods", [])]
    tables = []
    for heading, dimension in dimensions:
        selected = []
        for metric, label in KEY_METRICS:
            if metric not in info_by_metric:
                continue
            info = info_by_metric[metric]
            metric_dimension = info.get("dimension")
            if dimension == "temporal" and metric_dimension not in {
                "temporal",
                "motion",
            }:
                continue
            if dimension != "temporal" and metric_dimension != dimension:
                continue
            selected.append((metric, label, info))
        if not selected:
            continue
        rows = []
        for method_id in method_order:
            row = [labels.get(method_id, method_id)]
            for metric, _, _ in selected:
                row.append(
                    format_stat(metrics.get("aggregates", {}).get(method_id, {}).get(metric))
                )
            rows.append(row)
        headers = [tr(lang, "method")] + [
            f"{metric_label(lang, metric, info_by_metric[metric])} "
            f"{direction_symbol(metric, info_by_metric)}"
            for metric, label, _ in selected
        ]
        tables.append(
            {
                "heading": heading,
                "headers": headers,
                "rows": rows,
            }
        )
    return tables


def markdown_report(
    metrics: dict[str, Any],
    labels: dict[str, str],
    review_agg: dict[str, Any],
    status: str,
    findings: list[str],
    recommendation: str,
    args: argparse.Namespace,
    lang: str,
) -> str:
    s = TEXT[lang]
    na = "不适用" if lang == "zh" else "n/a"
    status_display = STATUS_ZH[status] if lang == "zh" else status
    lines = [
        f"# {args.title}",
        "",
        f"**{s['claim_status']}:** {status_display}  ",
        f"**{s['date']}:** {args.report_date}  ",
        f"**{s['claim']}:** {args.claim}",
        "",
        f"## {s['executive']}",
        "",
    ]
    lines.extend(f"- {finding}" for finding in findings)
    lines.extend(
        [
            "",
            f"## {s['protocol']}",
            "",
            f"| {s['gate']} | {s['value']} | {s['status']} |",
            "|---|---|---|",
        ]
    )
    for item, value, gate in evidence_rows(metrics, review_agg, status, lang):
        lines.append(f"| {item} | {value} | {gate} |")
    experiment = metrics.get("experiment", {})
    flow_implementation = experiment.get("flow_implementation", na)
    blind_value = experiment.get("blind", False)
    if lang == "zh":
        if flow_implementation == "OpenCV Farneback (diagnostic proxy)":
            flow_implementation = "OpenCV Farneback（诊断代理）"
        blind_value = "是" if blind_value else "否"
    lines.extend(
        [
            "",
            f"- {s['flow_implementation']}: {flow_implementation}",
            f"- {s['manifest_sha']}: `{metrics.get('manifest_sha256', na)}`",
            f"- {s['sample_frames']}: {experiment.get('frame_limit', na)}",
            f"- {s['max_side']}: {experiment.get('max_side', na)} px",
            f"- {s['temporal_offsets']}: {experiment.get('temporal_offsets', na)}",
            f"- {s['blinding']}: {blind_value}",
            "",
            f"## {s['dataset']}",
            "",
            f"| {s['case']} | {s['content']} | {s['style']} | {s['split']} | "
            f"{s['valid_methods']} | {s['warnings']} |",
            "|---|---|---|---|---|---|",
        ]
    )
    for case in metrics.get("cases", []):
        valid = [
            labels.get(method_id, method_id)
            for method_id, result in case.get("methods", {}).items()
            if result.get("valid")
        ]
        warnings = "; ".join(case.get("warnings", [])) or s["none"]
        lines.append(
            f"| {case.get('id')} | {case.get('content_id') or na} | "
            f"{case.get('style_id') or na} | {case.get('split')} | "
            f"{', '.join(valid)} | {warnings} |"
        )

    lines.extend(["", f"## {s['quantitative']}", ""])
    for table in metric_tables(metrics, labels, lang):
        lines.append(f"### {table['heading']}")
        lines.append("")
        lines.append("| " + " | ".join(table["headers"]) + " |")
        lines.append("|" + "---|" * len(table["headers"]))
        for row in table["rows"]:
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    lines.extend(
        [
            s["metrics_note"],
            "",
            f"## {s['blind_review']}",
            "",
        ]
    )
    if review_agg["scored_count"]:
        method_order = [method["id"] for method in metrics.get("methods", [])]
        lines.append("| " + " | ".join(s["review_table_headers"]) + " |")
        lines.append("|---|---|---|---|---|---|")
        for method_id in method_order:
            cells = [labels.get(method_id, method_id)]
            for dimension in REVIEW_DIMENSIONS:
                value = review_agg["method_dimension"][method_id][dimension]["mean"]
                cells.append(na if value is None else f"{value:.2f}/5")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        if review_agg["failure_counts"]:
            tags = ", ".join(
                f"{FAILURE_LABELS[lang].get(tag, tag.replace('_', ' '))} ({count})"
                for tag, count in review_agg["failure_counts"].most_common()
            )
            lines.append(f"{s['failure_tags']}: {tags}.")
        else:
            lines.append(s["no_failure_tags"])
        lines.append(
            f"\n{s['reviewer_records']}: {review_agg['reviewer_count']}. "
            f"{s['scored_records']}: {review_agg['scored_count']}. "
            f"{s['vlm_caveat']}"
        )
    else:
        lines.append(s["no_review"])

    lines.extend(["", f"## {s['per_case']}", ""])
    for case in metrics.get("cases", []):
        lines.append(f"### {case.get('id')}")
        lines.append("")
        lines.append("| " + " | ".join(s["per_case_headers"]) + " |")
        lines.append("|---|---|---|---|---|")
        for method_id, result in case.get("methods", {}).items():
            if not result.get("valid"):
                lines.append(
                    f"| {labels.get(method_id, method_id)} | {s['invalid']} | "
                    f"{s['invalid']} | {s['invalid']} | {s['invalid']} |"
                )
                continue
            values = result.get("metrics", {})
            lines.append(
                f"| {labels.get(method_id, method_id)} | "
                f"{format_number(values.get('ssim'))} | "
                f"{format_number(values.get('lab_palette_w1'))} | "
                f"{format_number(values.get('offset_1_warp_rmse'))} | "
                f"{format_number(values.get('offset_1_flow_epe'))} |"
            )
        if case.get("contact_sheet"):
            asset_name = Path(case["contact_sheet"]).name
            lines.extend(
                [
                    "",
                    f"![{s['contact_sheet']} {case.get('id')}](assets/{asset_name})",
                ]
            )
        lines.append("")

    lines.extend(
        [
            f"## {s['ablation']}",
            "",
            s["ablation_text"],
            "",
            f"## {s['failure_gallery']}",
            "",
            s["failure_text"],
        ]
    )
    lines.extend(["", f"## {s['threats']}", ""])
    lines.extend(f"- {threat}" for threat in s["threats_list"])
    lines.extend(["", f"## {s['conclusion']}", "", recommendation, ""])
    return "\n".join(lines)


def html_report(
    markdown_content: str,
    metrics: dict[str, Any],
    labels: dict[str, str],
    colors_by_method: dict[str, str],
    review_agg: dict[str, Any],
    status: str,
    findings: list[str],
    recommendation: str,
    args: argparse.Namespace,
    lang: str,
) -> str:
    s = TEXT[lang]
    na = "不适用" if lang == "zh" else "n/a"
    status_display = STATUS_ZH[status] if lang == "zh" else status
    table_html = []
    for table in metric_tables(metrics, labels, lang):
        header_cells = "".join(f"<th>{html.escape(cell)}</th>" for cell in table["headers"])
        body_rows = []
        for row in table["rows"]:
            cells = "".join(f"<td>{html.escape(cell)}</td>" for cell in row)
            body_rows.append(f"<tr>{cells}</tr>")
        table_html.append(
            f"<section><h3>{html.escape(table['heading'])}</h3>"
            f"<div class='table-wrap'><table><thead><tr>{header_cells}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody></table></div></section>"
        )

    review_cards = []
    if review_agg["scored_count"]:
        method_order = [method["id"] for method in metrics.get("methods", [])]
        for method_id in method_order:
            dimensions = review_agg["method_dimension"][method_id]
            bars = []
            for dimension in REVIEW_DIMENSIONS:
                value = dimensions[dimension]["mean"]
                width = 0 if value is None else value / 5 * 100
                bars.append(
                    "<div class='bar-row'>"
                    f"<span>{html.escape(DIMENSION_LABELS[lang][dimension])}</span>"
                    f"<div class='bar-track'><div class='bar-fill' style='width:{width:.1f}%'></div></div>"
                    f"<b>{na if value is None else f'{value:.2f}'}</b>"
                    "</div>"
                )
            review_cards.append(
                "<article class='review-card'>"
                f"<h3>{html.escape(labels.get(method_id, method_id))}</h3>"
                + "".join(bars)
                + "</article>"
            )
    else:
        review_cards.append(
            f"<p class='pending'>{html.escape(s['pending'])}</p>"
        )

    case_sections = []
    for case in metrics.get("cases", []):
        rows = []
        for method_id, result in case.get("methods", {}).items():
            metrics_values = result.get("metrics", {}) if result.get("valid") else {}
            rows.append(
                "<tr>"
                f"<td>{html.escape(labels.get(method_id, method_id))}</td>"
                f"<td>{html.escape(format_number(metrics_values.get('ssim')))}</td>"
                f"<td>{html.escape(format_number(metrics_values.get('lab_palette_w1')))}</td>"
                f"<td>{html.escape(format_number(metrics_values.get('offset_1_warp_rmse')))}</td>"
                f"<td>{html.escape(format_number(metrics_values.get('offset_1_flow_epe')))}</td>"
                "</tr>"
            )
        image = ""
        if case.get("contact_sheet"):
            asset_name = Path(case["contact_sheet"]).name
            image = f"<img src='assets/{html.escape(asset_name)}' alt='Contact sheet {html.escape(case.get('id', ''))}'>"
        case_sections.append(
            "<article class='case-card'>"
            f"<h3>{html.escape(case.get('id', ''))}</h3>"
            "<table><thead><tr>"
            + "".join(f"<th>{html.escape(header)}</th>" for header in s["per_case_headers"])
            + "</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>{image}</article>"
        )

    finding_html = "".join(f"<li>{html.escape(item)}</li>" for item in findings)
    evidence_html = "".join(
        "<tr>"
        f"<td>{html.escape(item)}</td><td>{html.escape(value)}</td>"
        f"<td><span class='gate'>{html.escape(gate)}</span></td></tr>"
        for item, value, gate in evidence_rows(metrics, review_agg, status, lang)
    )
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(args.title)}</title>
<style>
:root {{ --ink:#17212b; --muted:#607083; --line:#dbe2e9; --paper:#f5f7f9; --panel:#fff; --accent:#1d5c63; --warn:#b56224; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.65 "Segoe UI","Microsoft YaHei","PingFang SC","Noto Sans CJK SC",Arial,sans-serif; }}
main {{ max-width:1120px; margin:0 auto; padding:48px 36px 80px; }}
header {{ background:linear-gradient(125deg,#102a2f,#1d5c63 60%,#2d7c76); color:white; padding:52px; border-radius:22px; }}
header h1 {{ margin:0 0 14px; font-size:42px; line-height:1.08; letter-spacing:-1.2px; }}
header p {{ max-width:760px; margin:8px 0; color:#dce9e8; }}
.badge {{ display:inline-block; margin-top:18px; padding:7px 12px; border:1px solid #a9cbca; border-radius:999px; font-weight:700; letter-spacing:.4px; }}
section, .case-card {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:26px 30px; margin-top:24px; box-shadow:0 8px 26px rgba(24,43,55,.04); }}
h2 {{ font-size:25px; margin:0 0 18px; }} h3 {{ font-size:18px; margin:20px 0 10px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); gap:18px; }}
.finding {{ border-left:4px solid var(--accent); background:#eef6f5; padding:18px 20px; margin:10px 0; border-radius:0 10px 10px 0; }}
.table-wrap {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }} th {{ text-align:left; background:#f0f4f5; color:#314553; }}
th,td {{ padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }} .gate {{ font-weight:700; font-size:12px; }}
.review-card {{ border:1px solid var(--line); border-radius:12px; padding:20px; }}
.bar-row {{ display:grid; grid-template-columns:160px 1fr 42px; gap:12px; align-items:center; margin:10px 0; }}
.bar-track {{ height:9px; border-radius:999px; background:#e8edf0; overflow:hidden; }} .bar-fill {{ height:100%; background:linear-gradient(90deg,#2f8f78,#6db59b); }}
.case-card h3 {{ margin-top:0; }} .case-card img {{ width:100%; display:block; margin-top:18px; border-radius:9px; border:1px solid var(--line); }}
.pending {{ color:var(--muted); font-style:italic; }} .recommendation {{ background:#fff8ef; border-color:#ecd3b4; }}
.small {{ color:var(--muted); font-size:13px; }}
@media (max-width:700px) {{ main {{ padding:20px 12px 50px; }} header {{ padding:30px 22px; }} header h1 {{ font-size:31px; }} section,.case-card {{ padding:20px; }} .bar-row {{ grid-template-columns:110px 1fr 36px; font-size:12px; }} }}
</style>
</head>
<body><main>
<header>
<h1>{html.escape(args.title)}</h1>
<p><strong>{html.escape(s['claim'])}:</strong> {html.escape(args.claim)}</p>
<p><strong>{html.escape(s['date'])}:</strong> {html.escape(args.report_date)}</p>
<span class="badge">{html.escape(s['claim_status'])}: {html.escape(status_display)}</span>
</header>
<section><h2>{html.escape(s['executive'])}</h2><div class="grid">{''.join(f'<div class="finding">{html.escape(item)}</div>' for item in findings)}</div></section>
<section><h2>{html.escape(s['evidence_gates'])}</h2><div class="table-wrap"><table><thead><tr><th>{html.escape(s['gate'])}</th><th>{html.escape(s['value'])}</th><th>{html.escape(s['status'])}</th></tr></thead><tbody>{evidence_html}</tbody></table></div>
<p class="small">{html.escape(s['diagnostic_caveat'])}</p></section>
<section><h2>{html.escape(s['quantitative'])}</h2>{''.join(table_html)}<p class="small">{html.escape(s['metrics_note'])}</p></section>
<section><h2>{html.escape(s['blind_review'])}</h2><div class="grid">{''.join(review_cards)}</div></section>
<section><h2>{html.escape(s['per_case'])}</h2><p class="small">{html.escape(s['per_case_note'])}</p>{''.join(case_sections)}</section>
<section><h2>{html.escape(s['threats'])}</h2><ul>{''.join(f'<li>{html.escape(item)}</li>' for item in s['threats_list'])}</ul></section>
<section class="recommendation"><h2>{html.escape(s['recommendation'])}</h2><p>{html.escape(recommendation)}</p></section>
<p class="small">{html.escape(s['generated'])}</p>
</main></body></html>
"""


def fit_rl_image(path: Path, max_width: float, max_height: float) -> RLImage | None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return None
    scale = min(max_width / width, max_height / height)
    return RLImage(str(path), width=width * scale, height=height * scale)


def resolve_cjk_fonts(
    regular: Path | None,
    bold: Path | None,
) -> tuple[Path, Path]:
    env_regular = os.environ.get("VST_EVAL_CJK_FONT")
    regular_candidates = [
        Path(env_regular) if env_regular else None,
        Path(r"C:\Windows\Fonts\Deng.ttf"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    regular_path = regular
    if regular_path is None:
        regular_path = next(
            (path for path in regular_candidates if path and path.is_file()),
            None,
        )
    if regular_path is None or not regular_path.is_file():
        raise FileNotFoundError(
            "Chinese PDF output requires a CJK font. Pass --cjk-font PATH or set "
            "VST_EVAL_CJK_FONT. The font must use TrueType outlines; "
            "WenQuanYi Zen Hei is a portable Linux choice."
        )
    regular_path = regular_path.resolve()

    bold_path = bold
    if bold_path is None and regular_path.name.lower() == "deng.ttf":
        sibling = regular_path.with_name("Dengb.ttf")
        bold_path = sibling if sibling.is_file() else regular_path
    if bold_path is None:
        bold_path = regular_path
    if not bold_path.is_file():
        raise FileNotFoundError(f"CJK bold font not found: {bold_path}")
    return regular_path, bold_path.resolve()


def register_cjk_fonts(regular: Path, bold: Path) -> tuple[str, str]:
    regular_name = "VSTCJK"
    bold_name = "VSTCJK-Bold"
    try:
        if regular_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(regular_name, str(regular), subfontIndex=0))
        if bold_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(bold_name, str(bold), subfontIndex=0))
    except Exception as error:
        raise ValueError(
            f"Cannot embed CJK font '{regular}'. ReportLab requires TrueType outlines; "
            "use WenQuanYi Zen Hei or another TrueType-flavored TTF/TTC. "
            f"Original error: {error}"
        ) from error
    pdfmetrics.registerFontFamily(
        regular_name,
        normal=regular_name,
        bold=bold_name,
        italic=regular_name,
        boldItalic=bold_name,
    )
    return regular_name, bold_name


def pdf_safe_text(value: Any, lang: str = "en") -> str:
    """Avoid PDF core-font glyph gaps for direction annotations."""
    higher = "（越高越好）" if lang == "zh" else " (higher)"
    lower = "（越低越好）" if lang == "zh" else " (lower)"
    return (
        str(value)
        .replace("↑", higher)
        .replace("↓", lower)
        .replace("Δ", "Δ" if lang == "zh" else "d")
        .replace("•", "-")
    )


def pdf_table(
    headers: list[str],
    rows: list[list[str]],
    available_width: float,
    font_size: float = 7.3,
    font_regular: str = "Helvetica",
    font_bold: str = "Helvetica-Bold",
    lang: str = "en",
) -> Table:
    header_style = ParagraphStyle(
        "TableHeader",
        fontName=font_bold,
        fontSize=font_size,
        leading=font_size + 2,
        textColor=colors.white,
    )
    body_style = ParagraphStyle(
        "TableBody",
        fontName=font_regular,
        fontSize=font_size,
        leading=font_size + 2,
        textColor=colors.HexColor("#17212B"),
    )
    wrapped_headers = [
        Paragraph(html.escape(pdf_safe_text(cell, lang)), header_style)
        for cell in headers
    ]
    wrapped_rows = [
        [
            Paragraph(html.escape(pdf_safe_text(cell, lang)), body_style)
            for cell in row
        ]
        for row in rows
    ]
    first_col = min(available_width * 0.22, 112)
    remaining = (available_width - first_col) / max(1, len(headers) - 1)
    column_widths = [first_col] + [remaining] * (len(headers) - 1)
    table = Table(
        [wrapped_headers] + wrapped_rows,
        colWidths=column_widths,
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D5C63")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), font_bold),
                ("FONTNAME", (0, 1), (-1, -1), font_regular),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6DEE5")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8F9")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def pdf_report(
    output_path: Path,
    metrics: dict[str, Any],
    labels: dict[str, str],
    review_agg: dict[str, Any],
    status: str,
    findings: list[str],
    recommendation: str,
    args: argparse.Namespace,
    lang: str,
    font_regular: str,
    font_bold: str,
) -> None:
    s = TEXT[lang]
    na = "不适用" if lang == "zh" else "n/a"
    status_display = STATUS_ZH[status] if lang == "zh" else status
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=17 * mm,
        title=args.title,
        author="video-style-transfer-eval",
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "CoverTitle",
            parent=styles["Title"],
            fontName=font_bold,
            fontSize=27,
            leading=31,
            textColor=colors.HexColor("#102A2F"),
            alignment=TA_LEFT,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            "Section",
            parent=styles["Heading1"],
            fontName=font_bold,
            fontSize=17,
            leading=21,
            textColor=colors.HexColor("#1D5C63"),
            spaceBefore=12,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "Subsection",
            parent=styles["Heading2"],
            fontName=font_bold,
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#263946"),
            spaceBefore=8,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodySmall",
            parent=styles["BodyText"],
            fontName=font_regular,
            fontSize=8.3,
            leading=11.2,
            textColor=colors.HexColor("#314553"),
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodyCJK",
            parent=styles["BodyText"],
            fontName=font_regular,
            fontSize=9.4,
            leading=14,
            textColor=colors.HexColor("#17212B"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "Finding",
            parent=styles["BodyText"],
            fontName=font_regular,
            fontSize=9.2,
            leading=12.2,
            leftIndent=8,
            borderColor=colors.HexColor("#80AAA7"),
            borderWidth=0,
            backColor=colors.HexColor("#EEF6F5"),
            borderPadding=7,
            spaceAfter=6,
        )
    )

    story = []
    story.append(Spacer(1, 15 * mm))
    story.append(Paragraph(html.escape(args.title), styles["CoverTitle"]))
    story.append(
        Paragraph(
            f"<b>{html.escape(s['claim_status'])}:</b> {html.escape(status_display)}<br/>"
            f"<b>{html.escape(s['date'])}:</b> {html.escape(args.report_date)}<br/>"
            f"<b>{html.escape(s['claim'])}:</b> {html.escape(args.claim)}",
            styles["BodySmall"],
        )
    )
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(html.escape(s["executive"]), styles["Section"]))
    for finding in findings:
        story.append(Paragraph(html.escape(finding), styles["Finding"]))

    story.append(Paragraph(html.escape(s["evidence_gates"]), styles["Section"]))
    evidence = evidence_rows(metrics, review_agg, status, lang)
    story.append(
        pdf_table(
            [s["gate"], s["value"], s["status"]],
            [list(row) for row in evidence],
            178 * mm,
            font_regular=font_regular,
            font_bold=font_bold,
            lang=lang,
        )
    )
    story.append(
        Paragraph(
            "LAB 调色板距离与 Farneback 光流是确定性诊断代理，"
            "不能替代 RAFT、LPIPS、CLIP、FID 或 ArtFID。"
            if lang == "zh"
            else
            "LAB palette distance and Farneback flow are deterministic diagnostic "
            "proxies. They are not RAFT, LPIPS, CLIP, FID, or ArtFID.",
            styles["BodySmall"],
        )
    )

    story.append(Paragraph(html.escape(s["quantitative"]), styles["Section"]))
    for table_data in metric_tables(metrics, labels, lang):
        story.append(Paragraph(html.escape(table_data["heading"]), styles["Subsection"]))
        story.append(
            pdf_table(
                table_data["headers"],
                table_data["rows"],
                178 * mm,
                font_regular=font_regular,
                font_bold=font_bold,
                lang=lang,
            )
        )
        story.append(Spacer(1, 4 * mm))

    story.append(PageBreak())
    story.append(Paragraph(html.escape(s["blind_review"]), styles["Section"]))
    if review_agg["scored_count"]:
        rows = []
        for method in metrics.get("methods", []):
            method_id = method["id"]
            row = [labels.get(method_id, method_id)]
            for dimension in REVIEW_DIMENSIONS:
                value = review_agg["method_dimension"][method_id][dimension]["mean"]
                row.append(na if value is None else f"{value:.2f}/5")
            rows.append(row)
        story.append(
            pdf_table(
                [s["method"]]
                + [DIMENSION_LABELS[lang][dimension] for dimension in REVIEW_DIMENSIONS],
                rows,
                178 * mm,
                font_regular=font_regular,
                font_bold=font_bold,
                lang=lang,
            )
        )
        if review_agg["failure_counts"]:
            failure_text = ", ".join(
                f"{FAILURE_LABELS[lang].get(tag, tag.replace('_', ' '))} ({count})"
                for tag, count in review_agg["failure_counts"].most_common()
            )
            story.append(
                Paragraph(
                    f"<b>{html.escape(s['failure_tags'])}:</b> {html.escape(failure_text)}",
                    styles["BodySmall"],
                )
            )
        story.append(
            Paragraph(
                f"{s['reviewer_records']}: {review_agg['reviewer_count']}. "
                f"{s['scored_records']}: {review_agg['scored_count']}. "
                f"{s['vlm_caveat']}",
                styles["BodySmall"],
            )
        )
    else:
        story.append(
            Paragraph(
                html.escape(s["no_review"]),
                styles["BodySmall"],
            )
        )

    story.append(Paragraph(html.escape(s["per_case"]), styles["Section"]))
    for case in metrics.get("cases", []):
        story.append(Paragraph(html.escape(str(case.get("id"))), styles["Subsection"]))
        rows = []
        for method_id, result in case.get("methods", {}).items():
            values = result.get("metrics", {}) if result.get("valid") else {}
            rows.append(
                [
                    labels.get(method_id, method_id),
                    format_number(values.get("ssim")),
                    format_number(values.get("lab_palette_w1")),
                    format_number(values.get("offset_1_warp_rmse")),
                    format_number(values.get("offset_1_flow_epe")),
                ]
            )
        story.append(
            pdf_table(
                s["per_case_headers"],
                rows,
                178 * mm,
                font_regular=font_regular,
                font_bold=font_bold,
                lang=lang,
            )
        )
        if case.get("contact_sheet"):
            asset_path = output_path.parent / "assets" / Path(case["contact_sheet"]).name
            image = fit_rl_image(asset_path, 174 * mm, 92 * mm)
            if image:
                story.append(Spacer(1, 3 * mm))
                story.append(image)
        story.append(Spacer(1, 5 * mm))

    closing_block = [Paragraph(html.escape(s["threats"]), styles["Section"])]
    for threat in s["threats_list"]:
        closing_block.append(
            Paragraph(f"- {html.escape(threat)}", styles["BodySmall"])
        )
    closing_block.append(Paragraph(html.escape(s["recommendation"]), styles["Section"]))
    closing_block.append(Paragraph(html.escape(recommendation), styles["BodyCJK"]))
    story.append(KeepTogether(closing_block))

    def add_page_number(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont(font_regular, 7.5)
        canvas.setFillColor(colors.HexColor("#71808F"))
        canvas.drawString(16 * mm, 9 * mm, s["footer"])
        canvas.drawRightString(
            A4[0] - 16 * mm,
            9 * mm,
            (
                f"第 {document.page} 页"
                if lang == "zh"
                else f"Page {document.page}"
            ),
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)


def copy_contact_sheets(
    metrics: dict[str, Any],
    assets_dir: Path,
) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)
    for case in metrics.get("cases", []):
        source = case.get("contact_sheet")
        if not source:
            continue
        source_path = Path(source)
        if source_path.is_file():
            shutil.copy2(source_path, assets_dir / source_path.name)


def main() -> None:
    args = parse_args()
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    review = load_review(args.review)
    status = args.status or infer_status(metrics, review)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    copy_contact_sheets(metrics, args.output_dir / "assets")
    languages = ["en", "zh"] if args.language == "both" else [args.language]

    cjk_regular = "Helvetica"
    cjk_bold = "Helvetica-Bold"
    if "zh" in languages:
        regular_path, bold_path = resolve_cjk_fonts(
            args.cjk_font, args.cjk_font_bold
        )
        cjk_regular, cjk_bold = register_cjk_fonts(regular_path, bold_path)

    for lang in languages:
        render_args = copy.copy(args)
        render_args.title = (
            args.title_zh or tr("zh", "default_title")
            if lang == "zh"
            else args.title or tr("en", "default_title")
        )
        render_args.claim = (
            args.claim_zh or tr("zh", "default_claim")
            if lang == "zh"
            else args.claim or tr("en", "default_claim")
        )
        labels, colors_by_method = method_maps(metrics, lang)
        review_agg = aggregate_reviews(review, labels)
        findings = make_findings(
            metrics,
            labels,
            review_agg,
            args.primary,
            args.baseline,
            lang,
        )
        recommendation = decide_recommendation(
            metrics,
            labels,
            review_agg,
            args.primary,
            args.baseline,
            status,
            lang,
        )
        suffix = f"_{lang}" if args.language == "both" else ""
        markdown_path = args.output_dir / f"report{suffix}.md"
        html_path = args.output_dir / f"report{suffix}.html"
        pdf_path = args.output_dir / f"report{suffix}.pdf"
        markdown = markdown_report(
            metrics,
            labels,
            review_agg,
            status,
            findings,
            recommendation,
            render_args,
            lang,
        )
        markdown_path.write_text(markdown, encoding="utf-8")
        html_content = html_report(
            markdown,
            metrics,
            labels,
            colors_by_method,
            review_agg,
            status,
            findings,
            recommendation,
            render_args,
            lang,
        )
        html_path.write_text(html_content, encoding="utf-8")
        pdf_report(
            pdf_path,
            metrics,
            labels,
            review_agg,
            status,
            findings,
            recommendation,
            render_args,
            lang,
            cjk_regular if lang == "zh" else "Helvetica",
            cjk_bold if lang == "zh" else "Helvetica-Bold",
        )
        print(f"Wrote {markdown_path}")
        print(f"Wrote {html_path}")
        print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
