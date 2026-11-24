#!/usr/bin/env python3
"""Render a validated VST evaluation as Markdown, HTML, PDF, and XeLaTeX."""

from __future__ import annotations

import argparse
import copy
import html
import json
import math
import os
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import date, datetime
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
    ("csd_s", "CSD-S style consistency"),
    ("ssim", "SSIM"),
    ("psnr", "PSNR"),
    ("lpips", "LPIPS"),
    ("clip_f", "CLIP-F"),
    ("csd_c", "CSD-C content consistency"),
    ("lab_palette_w1", "LAB palette W1"),
    ("lab_ab_palette_w1", "LAB chroma W1"),
    ("offset_1_warp_rmse", "Warp RMSE, offset 1"),
    ("offset_5_warp_rmse", "Warp RMSE, offset 5"),
    ("offset_1_flow_epe", "Flow EPE, offset 1"),
    ("offset_1_flow_correlation", "Flow correlation, offset 1"),
    ("tlp", "tLP"),
    ("clip_cons", "CLIP-CONS"),
    ("luminance_flicker", "Luminance flicker"),
    ("vbench_subject_consistency", "VBench subject consistency"),
    ("vbench_background_consistency", "VBench background consistency"),
    ("vbench_temporal_flickering", "VBench temporal flickering"),
    ("vbench_motion_smoothness", "VBench motion smoothness"),
    ("vbench_dynamic_degree", "VBench dynamic degree"),
    ("vbench_aesthetic_quality", "VBench aesthetic quality"),
    ("vbench_imaging_quality", "VBench imaging quality"),
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
    "csd_s": "CSD-S 风格一致性",
    "csd_c": "CSD-C 内容一致性",
    "vbench_subject_consistency": "VBench 主体一致性",
    "vbench_background_consistency": "VBench 背景一致性",
    "vbench_temporal_flickering": "VBench 时序闪烁",
    "vbench_motion_smoothness": "VBench 运动平滑度",
    "vbench_dynamic_degree": "VBench 动态程度",
    "vbench_aesthetic_quality": "VBench 美学质量",
    "vbench_imaging_quality": "VBench 成像质量",
}

TEXT = {
    "en": {
        "default_title": "Video Style Transfer Evaluation",
        "default_claim": "Compare video style transfer quality while keeping style, content, motion, and temporal evidence separate.",
        "claim": "Claim",
        "claim_status": "Claim status",
        "date": "Date",
        "executive": "Executive verdict",
        "protocol": "Evaluation configuration",
        "metric_definitions": "Metric definitions and motivation",
        "metrics_glance": "Metrics at a glance",
        "key_results": "Key results",
        "key_dimension": "Dimension",
        "key_metric": "Headline metric",
        "key_primary": "Primary",
        "key_baseline": "Baseline",
        "key_delta": "Delta (favors primary)",
        "coverage": "Metric coverage",
        "coverage_note": "EchoStyle Table 1 parity, followed by the metric families measured in this run.",
        "parity_metric": "EchoStyle column",
        "parity_status": "Status",
        "parity_evidence": "Evidence",
        "status_present": "Provided",
        "status_proxy": "Proxy",
        "status_missing": "Missing",
        "family_metric": "Family",
        "family_count": "Metrics",
        "methods_count": "Methods",
        "cases_count": "Cases",
        "metrics_count": "Metrics",
        "reviewers_count": "VLM reviewers",
        "report_id_label": "Report ID",
        "evidence_label": "Evidence",
        "methods_list": "Methods",
        "data_count": "Count",
        "data_source": "Source",
        "metrics_by_category": "Metric configuration",
        "quantitative_metrics": "Quantitative metrics",
        "qualitative_metrics": "Qualitative metrics",
        "data_config": "Data configuration",
        "content_count": "Contents",
        "style_count": "Styles",
        "splits": "Splits",
        "mean_duration": "Mean clip duration",
        "resolutions": "Resolution",
        "data_warnings": "Warnings",
        "notes": "Notes",
        "review_model": "Review model",
        "tool_label": "Benchmark",
        "seed": "Seed",
        "setting": "Setting",
        "value": "Value",
        "value_label": "Value",
        "comment_label": "Conclusion",
        "key_bar": "Relative",
        "verdict": "Verdict",
        "better": "Better",
        "worse": "Worse",
        "tie": "Tie",
        "metric": "Metric",
        "dimension": "Dimension",
        "direction": "Direction",
        "unit": "Unit",
        "availability": "Availability",
        "appendix": "Appendix",
        "appendix_metric_definitions": "A. Metric definitions and motivation",
        "appendix_dataset": "B. Dataset and pairing",
        "appendix_per_case": "C. Per-case outcomes",
        "appendix_ablations": "D. Ablations and trade-offs",
        "appendix_failures": "E. Failure gallery",
        "appendix_threats": "F. Threats to validity",
        "motivation": "Motivation",
        "implementation": "Interpretation and reporting caveat",
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
        "metric": "Metric",
        "metrics_note": "Mean ± sample standard deviation over valid paired clips; the clip is the statistical unit. Bold and underlined values denote the best and second-best means. Arrows show preferred direction. n is listed in the evidence notes.",
        "diagnostic_caveat": "Farneback flow and LAB palette distance are diagnostic proxies. They are not RAFT, LPIPS, CLIP, FID, or ArtFID.",
        "discussion": "Analysis and discussion",
        "style_analysis": "Style fidelity",
        "content_analysis": "Content preservation",
        "temporal_analysis": "Motion and temporal stability",
        "quality_analysis": "Video quality (VBench)",
        "perceptual_analysis": "Perceptual review and failure modes",
        "cost_analysis": "Computational cost",
        "synthesis": "Synthesis",
        "paired_effects": "Paired comparison against the primary baseline",
        "best_second_note": "Best and second-best mean values are shown in bold and underlined, respectively.",
        "blind_review": "Qualitative assessment (VLM)",
        "artifacts": "Artifacts",
        "overall": "Overall",
        "failure_tags": "Failure tags",
        "no_failure_tags": "No failure tags were recorded in the reviewed sample.",
        "reviewer_records": "Reviewer records",
        "scored_records": "Scored case/method records",
        "vlm_caveat": "VLM scores are perceptual evidence, not ground truth.",
        "no_review": "No validated blinded VLM review is present. Visual claims remain pending.",
        "per_case": "Case study",
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
        "conclusion": "Conclusion",
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
        "date": "时间",
        "executive": "执行摘要",
        "protocol": "评估配置",
        "metric_definitions": "指标定义与设计动机",
        "metrics_glance": "指标速览",
        "key_results": "关键结果",
        "key_dimension": "维度",
        "key_metric": "代表指标",
        "key_primary": "主方法",
        "key_baseline": "基线",
        "key_delta": "差值（正数利于主方法）",
        "coverage": "指标覆盖",
        "coverage_note": "先给 EchoStyle 表 1 的覆盖情况，再列本次运行实际测度的指标族。",
        "parity_metric": "EchoStyle 列",
        "parity_status": "状态",
        "parity_evidence": "证据",
        "status_present": "已提供",
        "status_proxy": "代理",
        "status_missing": "缺失",
        "family_metric": "指标族",
        "family_count": "指标数",
        "methods_count": "方法数",
        "cases_count": "数据量",
        "metrics_count": "指标数",
        "reviewers_count": "VLM 评审",
        "report_id_label": "报告 ID",
        "evidence_label": "证据",
        "methods_list": "与试方法",
        "data_count": "数量",
        "data_source": "来源",
        "metrics_by_category": "指标配置",
        "quantitative_metrics": "定量指标",
        "qualitative_metrics": "定性指标",
        "data_config": "数据配置",
        "content_count": "内容数",
        "style_count": "风格数",
        "splits": "划分",
        "mean_duration": "平均时长",
        "resolutions": "分辨率",
        "data_warnings": "警告",
        "notes": "备注",
        "review_model": "评审模型",
        "tool_label": "基准",
        "seed": "随机种子",
        "setting": "配置项",
        "value": "取值",
        "value_label": "取值",
        "comment_label": "结论",
        "key_bar": "相对强度",
        "verdict": "结论",
        "better": "更优",
        "worse": "更差",
        "tie": "持平",
        "metric": "指标",
        "dimension": "维度",
        "direction": "方向",
        "unit": "单位",
        "availability": "可用性",
        "appendix": "附录",
        "appendix_metric_definitions": "A. 指标定义与设计动机",
        "appendix_dataset": "B. 数据集与配对",
        "appendix_per_case": "C. 单案例结果",
        "appendix_ablations": "D. 消融与权衡",
        "appendix_failures": "E. 失败案例",
        "appendix_threats": "F. 有效性威胁",
        "motivation": "设计动机",
        "implementation": "解释与报告注意事项",
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
        "metric": "指标",
        "metrics_note": "表中为有效配对片段上的平均值 ± 样本标准差，统计单位为片段。粗体和下划线分别表示最优和次优均值，箭头表示指标偏好方向。",
        "diagnostic_caveat": "Farneback 光流与 LAB 调色板距离是诊断代理，不能替代 RAFT、LPIPS、CLIP、FID 或 ArtFID。",
        "discussion": "分析与讨论",
        "style_analysis": "风格保真度",
        "content_analysis": "内容保持",
        "temporal_analysis": "运动与时序稳定性",
        "quality_analysis": "视频质量（VBench）",
        "perceptual_analysis": "感知审查与失败模式",
        "cost_analysis": "计算成本",
        "synthesis": "综合判断",
        "paired_effects": "相对主基线的配对比较",
        "best_second_note": "最优和次优均值分别以粗体和下划线标出。",
        "blind_review": "定性评估（VLM）",
        "artifacts": "伪影",
        "overall": "整体",
        "failure_tags": "失败标签",
        "no_failure_tags": "本次审查样本未记录失败标签。",
        "reviewer_records": "审查记录数",
        "scored_records": "已评分案例/方法记录",
        "vlm_caveat": "VLM 评分是感知证据，不是真实标签。",
        "no_review": "当前没有经过校验的盲评 VLM 记录，视觉结论仍待补充。",
        "per_case": "案例分析",
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
        "conclusion": "结论",
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


METRIC_DEFINITIONS = [
    {
        "id": "ssim",
        "name_en": "SSIM",
        "name_zh": "SSIM 结构相似度",
        "available_keys": ["ssim"],
        "formula": "SSIM(x,y) = ((2*mu_x*mu_y + C1)*(2*sigma_xy + C2)) / ((mu_x^2 + mu_y^2 + C1)*(sigma_x^2 + sigma_y^2 + C2))",
        "formula_tex": r"\mathrm{SSIM}(x,y)=\frac{(2\mu_x\mu_y+C_1)(2\sigma_{xy}+C_2)}{(\mu_x^2+\mu_y^2+C_1)(\sigma_x^2+\sigma_y^2+C_2)}",
        "rationale_en": "SSIM compares local luminance, contrast, and structure instead of raw pixel error. It is useful for detecting geometric and structural changes, but strong stylization legitimately changes contrast and texture.",
        "rationale_zh": "SSIM 比较局部亮度、对比度和结构，而不是原始像素误差。它适合检测几何和结构变化，但强风格化本身也会改变对比度与纹理。",
        "caveat_en": "Interpret it as a content diagnostic, not a perceptual style score.",
        "caveat_zh": "应将其视为内容诊断，而不是感知风格分数。",
    },
    {
        "id": "psnr",
        "name_en": "PSNR",
        "name_zh": "PSNR 峰值信噪比",
        "available_keys": ["psnr"],
        "formula": "PSNR = 10 * log10(MAX^2 / MSE)",
        "formula_tex": r"\mathrm{PSNR}=10\log_{10}\!\left(\frac{\mathrm{MAX}^2}{\mathrm{MSE}}\right)",
        "rationale_en": "PSNR converts mean squared error into a logarithmic scale and gives a quick, deterministic fidelity diagnostic. It is sensitive to global color shifts, compression, and resolution differences.",
        "rationale_zh": "PSNR 将均方误差转换为对数尺度，提供快速、确定性的保真度诊断。它对全局颜色变化、压缩和分辨率差异较敏感。",
        "caveat_en": "Do not treat a small PSNR change as a proportional change in perceived quality.",
        "caveat_zh": "不能把 PSNR 的小幅变化直接解释为感知质量的等比例变化。",
    },
    {
        "id": "lpips",
        "name_en": "LPIPS",
        "name_zh": "LPIPS 感知距离",
        "available_keys": ["lpips"],
        "formula": "LPIPS(x,y) = sum_l (1/(H_l*W_l)) * sum_hw ||w_l * (phi_l(x)_hw - phi_l(y)_hw)||^2",
        "formula_tex": r"\mathrm{LPIPS}(x,y)=\sum_l\frac{1}{H_lW_l}\sum_{h,w}\left\|w_l\odot(\hat\phi_l(x)_{h,w}-\hat\phi_l(y)_{h,w})\right\|_2^2",
        "rationale_en": "LPIPS compares normalized deep features and aligns better with perceptual similarity than pixel metrics. It is preferred as preservation evidence when a fixed LPIPS implementation is available.",
        "rationale_zh": "LPIPS 比较归一化深层特征，通常比像素指标更符合人类感知相似性。在有固定 LPIPS 实现时，应优先作为内容保持证据。",
        "caveat_en": "The network, preprocessing, and weights must be identical across every compared method.",
        "caveat_zh": "所有比较方法必须使用相同的网络、预处理和权重。",
    },
    {
        "id": "clip_f",
        "name_en": "CLIP-F",
        "name_zh": "CLIP-F 内容语义相似度",
        "available_keys": ["clip_f"],
        "formula": "CLIP-F(R,I) = 100 * cos(phi_I(R), phi_I(I))",
        "formula_tex": r"\mathrm{CLIP\text{-}F}(R,I)=100\cos\!\left(\phi_I(R),\phi_I(I)\right)",
        "rationale_en": "CLIP-F measures whether the stylized and original frames retain the same image-level semantics. It complements structure metrics when appearance changes substantially.",
        "rationale_zh": "CLIP-F 衡量风格化帧与源帧是否保留相同的图像级语义。当外观变化较大时，它可以补充结构指标。",
        "caveat_en": "Image-level embeddings can miss local identity, boundary, and occlusion errors.",
        "caveat_zh": "图像级嵌入可能遗漏局部身份、边界和遮挡错误。",
    },
    {
        "id": "clip_i",
        "name_en": "CLIP-I",
        "name_zh": "CLIP-I 风格图像相似度",
        "available_keys": ["clip_i"],
        "formula": "CLIP-I(R,S) = 100 * cos(phi_I(R), phi_I(S))",
        "formula_tex": r"\mathrm{CLIP\text{-}I}(R,S)=100\cos\!\left(\phi_I(R),\phi_I(S)\right)",
        "rationale_en": "CLIP-I provides a content-robust global signal for whether the generated frame and style reference occupy a similar semantic visual space. It is one component of style evidence, not a texture-transfer proof.",
        "rationale_zh": "CLIP-I 提供对内容变化较稳健的全局信号，用于判断生成帧与风格参考是否位于相近的语义视觉空间。它只是风格证据的一部分，不能单独证明纹理迁移成功。",
        "caveat_en": "Report it comparatively and supplement it with texture-specific features or blinded review.",
        "caveat_zh": "应进行相对比较，并结合纹理特征或盲评审查。",
    },
    {
        "id": "fid",
        "name_en": "FID",
        "name_zh": "FID 分布距离",
        "available_keys": ["fid"],
        "formula": "FID = ||mu_s - mu_g||_2^2 + Tr(S_s + S_g - 2*(S_s*S_g)^(1/2))",
        "formula_tex": r"\mathrm{FID}=\left\|\mu_s-\mu_g\right\|_2^2+\operatorname{Tr}\!\left(\Sigma_s+\Sigma_g-2(\Sigma_s\Sigma_g)^{1/2}\right)",
        "rationale_en": "FID compares Inception feature distributions, so it can capture style-set mismatch beyond single-image color statistics. It requires a meaningful distribution of reference and generated frames.",
        "rationale_zh": "FID 比较 Inception 特征分布，因此能捕捉超出单图颜色统计的风格集合差异。它需要足够数量的参考和生成帧来估计分布。",
        "caveat_en": "A single style image is not a valid FID style distribution. Record image count, resolution, and preprocessing.",
        "caveat_zh": "单张风格图不能构成有效的 FID 风格分布。必须记录图像数量、分辨率和预处理。",
    },
    {
        "id": "artfid",
        "name_en": "ArtFID",
        "name_zh": "ArtFID 联合风格-内容距离",
        "available_keys": ["artfid"],
        "formula": "ArtFID = (1 + mean_i LPIPS(I_i,R_i)) * (1 + FID(R,S))",
        "formula_tex": r"\mathrm{ArtFID}=\left(1+\frac{1}{N}\sum_i\mathrm{LPIPS}(I_i,R_i)\right)\left(1+\mathrm{FID}(R,S)\right)",
        "rationale_en": "ArtFID combines perceptual content preservation and style-distribution distance in one number. The product makes a method visible when it improves one factor while degrading the other.",
        "rationale_zh": "ArtFID 将感知内容保持和风格分布距离结合为一个数值。乘积形式会让“一个因素改善、另一个因素退化”的方法暴露出来。",
        "caveat_en": "Do not use it unless its LPIPS and FID components follow the cited, fixed implementation.",
        "caveat_zh": "除非 LPIPS 和 FID 分量遵循固定的引用实现，否则不要使用该指标。",
    },
    {
        "id": "lab_palette_w1",
        "name_en": "LAB palette W1",
        "name_zh": "LAB 调色板 W1",
        "available_keys": ["lab_palette_w1", "lab_ab_palette_w1"],
        "formula": "W1_c = sum_k |CDF_frame,c(k) - CDF_style,c(k)| / 255;  PaletteW1 = 100 * mean_c W1_c",
        "formula_tex": r"W_{1,c}=\frac{1}{255}\sum_{k=0}^{255}\left|F^{\mathrm{frame}}_c(k)-F^{\mathrm{style}}_c(k)\right|,\qquad \mathrm{PaletteW1}=100\cdot\frac{1}{|C|}\sum_{c\in C}W_{1,c}",
        "rationale_en": "This inexpensive diagnostic summarizes marginal LAB color alignment. It is useful for detecting global recoloring and palette mismatch before expensive perceptual metrics.",
        "rationale_zh": "该低成本的诊断指标概括 LAB 颜色边缘分布的一致性，可在运行昂贵感知指标前发现全局着色和调色板不匹配。",
        "caveat_en": "It does not measure brushwork, texture attachment, composition, or style semantics.",
        "caveat_zh": "它不衡量笔触、纹理附着、构图或风格语义。",
    },
    {
        "id": "warp_rmse",
        "name_en": "Source-flow warping RMSE",
        "name_zh": "源光流重映射 RMSE",
        "available_keys": [
            "offset_1_warp_rmse",
            "offset_5_warp_rmse",
            "offset_1_warp_mae",
            "offset_5_warp_mae",
            "offset_1_occlusion_ratio",
            "offset_5_occlusion_ratio",
        ],
        "formula": "WarpRMSE_d = sqrt(sum_x M_t(x)*||R_t(x) - W(R_(t+d))(x)||_2^2 / sum_x M_t(x))",
        "formula_tex": r"\mathrm{WarpRMSE}_{\Delta}=\sqrt{\frac{\sum_x M_t(x)\left\|R_t(x)-W(R_{t+\Delta})(x)\right\|_2^2}{\sum_x M_t(x)}}",
        "rationale_en": "Source optical flow supplies the expected motion. Warping a later output frame back with that flow isolates drift and flicker from legitimate scene motion; occluded pixels are masked.",
        "rationale_zh": "源视频光流提供预期运动。使用该光流将后续输出帧重映射回当前帧，可以将漂移和闪烁与正常场景运动分开，并屏蔽遮挡像素。",
        "caveat_en": "The result inherits the flow estimator's errors; Farneback is a diagnostic proxy, not RAFT.",
        "caveat_zh": "结果会继承光流估计器的误差；Farneback 是诊断代理，不是 RAFT。",
    },
    {
        "id": "flow_epe",
        "name_en": "Flow endpoint error",
        "name_zh": "光流端点误差",
        "available_keys": ["offset_1_flow_epe", "offset_5_flow_epe"],
        "formula": "EPE_d = (1/|Omega|) * sum_{x in Omega} ||F_R(x) - F_I(x)||_2",
        "formula_tex": r"\mathrm{EPE}_{\Delta}=\frac{1}{|\Omega|}\sum_{x\in\Omega}\left\|F^R_t(x)-F^I_t(x)\right\|_2",
        "rationale_en": "EPE measures whether stylization changes the estimated displacement between frames. It is sensitive to motion alteration and can reveal propagation failures that still images miss.",
        "rationale_zh": "EPE 衡量风格化是否改变帧间估计位移，可揭示静态图像难以发现的运动改变和传播失败。",
        "caveat_en": "Texture changes can create spurious flow; use the same estimator and occlusion handling for every method.",
        "caveat_zh": "纹理变化可能产生虚假光流；所有方法必须使用相同估计器和遮挡处理。",
    },
    {
        "id": "flow_corr",
        "name_en": "Flow-field correlation",
        "name_zh": "光流场相关性",
        "available_keys": ["offset_1_flow_correlation", "offset_5_flow_correlation"],
        "formula": "rho_d = corr(flatten(F_R), flatten(F_I))",
        "formula_tex": r"\rho_{\Delta}=\operatorname{corr}\!\left(\operatorname{vec}(F^R_t),\operatorname{vec}(F^I_t)\right)",
        "rationale_en": "Correlation measures agreement in motion direction independently of the flow magnitude emphasized by EPE. Together they separate directional corruption from displacement scaling.",
        "rationale_zh": "相关性衡量运动方向的一致性，相比 EPE 更少受幅度影响。两者结合可以区分方向错误和位移尺度变化。",
        "caveat_en": "It is a global summary and may hide localized motion errors.",
        "caveat_zh": "这是一个全局概括，可能掩盖局部运动错误。",
    },
    {
        "id": "tlp",
        "name_en": "Temporal LPIPS (tLP)",
        "name_zh": "时序 LPIPS（tLP）",
        "available_keys": ["tlp"],
        "formula": "tLP = (1/(T-d)) * sum_t LPIPS(R_t, W(R_(t+d)))",
        "formula_tex": r"\mathrm{tLP}=\frac{1}{T-\Delta}\sum_t\mathrm{LPIPS}\!\left(R_t,W(R_{t+\Delta})\right)",
        "rationale_en": "tLP replaces pixel error in warping analysis with a perceptual deep-feature error, making texture and structure instability easier to detect than raw L2 differences.",
        "rationale_zh": "tLP 在重映射分析中用深层特征感知误差替代像素误差，使纹理和结构不稳定性比原始 L2 差值更容易被检测。",
        "caveat_en": "Use a fixed LPIPS network and report the temporal offset.",
        "caveat_zh": "必须使用固定的 LPIPS 网络并报告时间偏移。",
    },
    {
        "id": "clip_cons",
        "name_en": "CLIP temporal consistency",
        "name_zh": "CLIP 时序一致性",
        "available_keys": ["clip_cons"],
        "formula": "CLIP-CONS = 100 * cos(phi(R_t+1)-phi(R_t), phi(I_t+1)-phi(I_t))",
        "formula_tex": r"\mathrm{CLIP\text{-}CONS}=100\cos\!\left(\phi(R_{t+1})-\phi(R_t),\phi(I_{t+1})-\phi(I_t)\right)",
        "rationale_en": "CLIP-CONS asks whether semantic change between adjacent stylized frames follows the semantic change in the source. It complements pixel warping when content is stylized heavily.",
        "rationale_zh": "CLIP-CONS 检查相邻风格化帧的语义变化是否与源视频一致。当内容被强风格化时，它可以补充像素重映射指标。",
        "caveat_en": "It measures semantic change agreement, not spatial alignment or flicker.",
        "caveat_zh": "它衡量语义变化一致性，而不是空间对齐或闪烁。",
    },
    {
        "id": "flicker",
        "name_en": "Detrended luminance flicker",
        "name_zh": "去趋势亮度闪烁",
        "available_keys": ["luminance_flicker"],
        "formula": "F = sqrt((1/T) * sum_t (l_t - (a*t+b))^2), where l_t is frame mean luminance",
        "formula_tex": r"F=\sqrt{\frac{1}{T}\sum_t\left(l_t-(at+b)\right)^2},\quad l_t=\operatorname{mean}(\operatorname{luma}(R_t))",
        "rationale_en": "Removing a linear luminance trend distinguishes intentional exposure or scene changes from abrupt global flicker. The measure is cheap and directly targets one common VST artifact.",
        "rationale_zh": "去除线性亮度趋势可以区分合理的曝光变化和突发全局闪烁。该指标成本低，直接针对常见的视频风格迁移伪影。",
        "caveat_en": "It ignores local flicker and texture sticking, which require motion-aware or visual review.",
        "caveat_zh": "它忽略局部闪烁和纹理粘连，这些需要运动感知指标或视觉审查。",
    },
    {
        "id": "vlm",
        "name_en": "Blinded VLM score",
        "name_zh": "盲评 VLM 分数",
        "available_keys": [],
        "formula": "S_d,m = (1/R) * sum_r (1/|C_valid|) * sum_c s_(r,c,m,d), s in {1,2,3,4,5}",
        "formula_tex": r"\bar S_{d,m}=\frac{1}{R}\sum_{r=1}^{R}\frac{1}{|C_{\mathrm{valid}}|}\sum_{c\in C_{\mathrm{valid}}}s_{r,c,m,d},\quad s\in\{1,\ldots,5\}",
        "rationale_en": "The rubric captures style adherence, content preservation, temporal stability, artifact control, and overall quality when automated metrics cannot separate texture and motion failures. Per-case blinded labels reduce method-identity bias.",
        "rationale_zh": "该评分标准覆盖风格一致性、内容保持、时序稳定性、伪影控制和整体质量，能补充自动指标难以区分的纹理与运动故障。逐案例盲化方法标签可降低方法身份偏差。",
        "caveat_en": "VLM judgments are perceptual evidence, not ground truth; record model version and use multiple independent reviewers for paper-level claims.",
        "caveat_zh": "VLM 判断是感知证据而非真实标签；应记录模型版本，并使用多个独立审查者支持论文级结论。",
    },
    {
        "id": "cost",
        "name_en": "Runtime and peak memory",
        "name_zh": "运行时间与峰值显存",
        "available_keys": ["runtime_s", "peak_memory_gb"],
        "formula": "Runtime_m = mean_c t_(c,m); PeakMemory_m = max_c peak_(c,m)",
        "formula_tex": r"\mathrm{Runtime}_m=\frac{1}{|C|}\sum_c t_{c,m},\qquad \mathrm{PeakMem}_m=\max_c p_{c,m}",
        "rationale_en": "Quality comparisons are incomplete without deployment cost. Mean runtime captures expected latency, while maximum peak memory captures the worst observed resource requirement.",
        "rationale_zh": "如果缺少部署成本，质量比较并不完整。平均运行时间反映预期延迟，最大峰值显存反映最差观测资源需求。",
        "caveat_en": "Measure on identical hardware, precision, resolution, and batch settings; report both mean and peak.",
        "caveat_zh": "必须在相同硬件、精度、分辨率和批设置下测量，并同时报告均值和峰值。",
    },
    {
        "id": "csd_s",
        "name_en": "CSD-S style consistency",
        "name_zh": "CSD-S 风格一致性",
        "available_keys": ["csd_s"],
        "formula": "CSD-S = (1/(T-1)) * sum_{t=1}^{T-1} cos(s(f_t), s(f_0))",
        "formula_tex": r"\mathrm{CSD\text{-}S}=\frac{1}{T-1}\sum_{t=1}^{T-1}\cos\!\left(s(f_t),s(f_0)\right)",
        "rationale_en": "CSD (contrastive style descriptor) is a CLIP ViT-L/14 image encoder with separate style and content projection heads trained for content-style disentanglement; s(.) is the style head. Comparing every later frame with the first frame measures style drift without folding in content change, which is the 'Style Consis.' column reported by EchoStyle (ECCV 2026).",
        "rationale_zh": "CSD（对比式风格描述子）以 CLIP ViT-L/14 图像编码器为骨干，训练出彼此分离的风格头 s(·) 与内容头 c(·)。将后续每一帧与首帧比较，可以在不混入内容变化的情况下度量风格漂移，对应 EchoStyle（ECCV 2026）报告中的“Style Consis.”列。",
        "caveat_en": "The score is image-level and does not localize drift. Fix the CSD checkpoint, the CLIP preprocessing, and the frame sampling for every method; absolute cosine values are not comparable across different CSD variants.",
        "caveat_zh": "该分数是图像级汇总，无法定位漂移位置。所有方法必须固定 CSD checkpoint、CLIP 预处理和抽帧方式；不同 CSD 变体的绝对余弦值不可直接比较。",
    },
    {
        "id": "csd_c",
        "name_en": "CSD-C content consistency",
        "name_zh": "CSD-C 内容一致性",
        "available_keys": ["csd_c"],
        "formula": "CSD-C = (1/(T-1)) * sum_{t=1}^{T-1} cos(c(f_t), c(f_0))",
        "formula_tex": r"\mathrm{CSD\text{-}C}=\frac{1}{T-1}\sum_{t=1}^{T-1}\cos\!\left(c(f_t),c(f_0)\right)",
        "rationale_en": "The content head of the same disentangled CSD model gives the companion drift signal. Separating CSD-S from CSD-C distinguishes a method that keeps its style but slowly melts the content from one that loses both.",
        "rationale_zh": "同一套解耦 CSD 模型的内容头提供配套的漂移信号。将 CSD-S 与 CSD-C 分开报告，可以区分“风格保持但内容逐渐融化”与“风格和内容一起丢失”两种失效模式。",
        "caveat_en": "The content head is a semantic embedding, not a geometric or temporal model. Pair it with source-flow warping error and CLIP-F before concluding that content was preserved.",
        "caveat_zh": "内容头是语义嵌入，不是几何或时序模型。在得出“内容得到保持”的结论前，应结合源光流重映射误差与 CLIP-F。",
    },
    {
        "id": "vbench_subject_consistency",
        "name_en": "VBench subject consistency",
        "name_zh": "VBench 主体一致性",
        "available_keys": ["vbench_subject_consistency"],
        "formula": "SubjectCons = (1/(T-1)) * sum_t cos(d(f_t), d(f_(t+1))), d = DINO ViT-S/16",
        "formula_tex": r"\mathrm{SubjectCons}=\frac{1}{T-1}\sum_{t=1}^{T-1}\cos\!\left(d(f_t),d(f_{t+1})\right),\quad d=\mathrm{DINO\text{-}ViT\text{-}S/16}",
        "rationale_en": "VBench uses DINO features to ask whether the same subject survives across frames. In video stylization this catches identity morphing and subject-level flicker that palette and pixel metrics miss.",
        "rationale_zh": "VBench 使用 DINO 特征判断同一主体是否在帧间保持一致。在视频风格化中，该指标可以捕捉调色板与像素指标遗漏的主体身份变形和主体级闪烁。",
        "caveat_en": "It rewards static clips, because an unchanged subject always scores high. Read it together with dynamic degree and motion smoothness, and remember that custom-input VBench runs are not leaderboard-comparable.",
        "caveat_zh": "该指标偏袒静态片段：主体不变时天然得分高。应与动态程度和运动平滑度一起解读，并注意 custom_input 模式下的 VBench 结果不能与官方榜单直接比较。",
    },
    {
        "id": "vbench_background_consistency",
        "name_en": "VBench background consistency",
        "name_zh": "VBench 背景一致性",
        "available_keys": ["vbench_background_consistency"],
        "formula": "BgCons = (1/(T-1)) * sum_t cos(c(f_t), c(f_(t+1))), c = CLIP ViT-B/32",
        "formula_tex": r"\mathrm{BgCons}=\frac{1}{T-1}\sum_{t=1}^{T-1}\cos\!\left(c(f_t),c(f_{t+1})\right),\quad c=\mathrm{CLIP\text{-}ViT\text{-}B/32}",
        "rationale_en": "Background consistency tracks whether the scene context drifts or pops between frames. It complements subject consistency: a method can hold the person while repainting the room behind them.",
        "rationale_zh": "背景一致性衡量场景上下文在帧间是否漂移或跳变，与主体一致性互补：方法可能保持人物不变，却在重新绘制其背后的房间。",
        "caveat_en": "CLIP features are coarse and can still mix subject and background; treat the split between subject and background as indicative, not exact.",
        "caveat_zh": "CLIP 特征较粗糙，仍可能混合主体与背景；主体/背景的区分只能视为指示性而非精确划分。",
    },
    {
        "id": "vbench_temporal_flickering",
        "name_en": "VBench temporal flickering",
        "name_zh": "VBench 时序闪烁",
        "available_keys": ["vbench_temporal_flickering"],
        "formula": "Flicker = 1 - (1/(T-1)) * sum_t mean|I_(t+1) - I_t|, I in [0,1]",
        "formula_tex": r"\mathrm{Flicker}=1-\frac{1}{T-1}\sum_{t=1}^{T-1}\operatorname{mean}\left|I_{t+1}-I_t\right|",
        "rationale_en": "VBench's pixel-level static consistency term penalizes sudden global changes between adjacent frames. It is a useful sanity check on the diagnostic luminance-flicker measure because it reacts to any channel, not only luma.",
        "rationale_zh": "VBench 的像素级静态一致性项惩罚相邻帧之间的突发全局变化。它可作为诊断性亮度闪烁指标的交叉验证，因为它对全部通道敏感，而不只是亮度。",
        "caveat_en": "Pixel differences also punish legitimate fast motion and hard cuts. Do not rank a dynamic clip against a static clip on this metric alone.",
        "caveat_zh": "像素差异同样会惩罚合理的快速运动和硬切。不能仅凭该指标把动态片段与静态片段放在一起排名。",
    },
    {
        "id": "vbench_motion_smoothness",
        "name_en": "VBench motion smoothness",
        "name_zh": "VBench 运动平滑度",
        "available_keys": ["vbench_motion_smoothness"],
        "formula": "MotionSmooth = 1 - (1/(T-2)) * sum_t ||I_t - AMT(I_(t-1), I_(t+1))||^2",
        "formula_tex": r"\mathrm{MotionSmooth}=1-\frac{1}{T-2}\sum_{t=2}^{T-1}\left\|I_t-\mathrm{AMT}(I_{t-1},I_{t+1})\right\|_2^2",
        "rationale_en": "VBench interpolates held-out frames with AMT and treats interpolation error as a smoothness signal. Unlike source-to-output flow metrics it does not need a paired source, so it also works when only generated videos are available.",
        "rationale_zh": "VBench 用 AMT 对留出帧做插值，并把插值误差作为平滑度信号。与源到输出的光流指标不同，它不需要配对源视频，因此在只有生成视频时也能使用。",
        "caveat_en": "The score depends on the AMT checkpoint and partly rewards motion blur or oversmoothing; a blurry result can look 'smooth'.",
        "caveat_zh": "该分数依赖 AMT checkpoint，并会部分奖励运动模糊或过度平滑；模糊的结果可能显得“平滑”。",
    },
    {
        "id": "vbench_dynamic_degree",
        "name_en": "VBench dynamic degree",
        "name_zh": "VBench 动态程度",
        "available_keys": ["vbench_dynamic_degree"],
        "formula": "DynDegree = (1/|V|) * sum_v 1[mean flow magnitude(v) > tau]",
        "formula_tex": r"\mathrm{DynDegree}=\frac{1}{|V|}\sum_{v\in V}\mathbf{1}\!\left[\overline{\left|F_v\right|}>\tau\right]",
        "rationale_en": "Dynamic degree reports the fraction of clips with enough estimated motion to be considered dynamic. It is VBench's guard against models that pass consistency metrics by generating nearly static videos.",
        "rationale_zh": "动态程度报告被判定为具有足够运动量的片段比例，是 VBench 用来防止模型通过生成近乎静止的视频来“通过”一致性指标的护栏。",
        "caveat_en": "Higher is not automatically better: exaggerated motion raises the score while damaging content fidelity. Compare only clips with comparable source motion.",
        "caveat_zh": "并非越高越好：夸张运动会提高该分数，却损害内容保真度。只能在源运动量可比的片段之间比较。",
    },
    {
        "id": "vbench_aesthetic_quality",
        "name_en": "VBench aesthetic quality",
        "name_zh": "VBench 美学质量",
        "available_keys": ["vbench_aesthetic_quality"],
        "formula": "Aesthetic = (1/T) * sum_t LAION-Aesthetic(I_t)",
        "formula_tex": r"\mathrm{Aesthetic}=\frac{1}{T}\sum_{t=1}^{T}\mathrm{LAION\text{-}Aesthetic}(I_t)",
        "rationale_en": "The LAION aesthetic predictor supplies a learned preference score per frame. It is one of the few public signals for the 'does it look good' question that pixel fidelity metrics cannot answer.",
        "rationale_zh": "LAION 美学预测器为每帧提供学习到的偏好分数，是少数能回答“看起来是否好看”这一像素保真指标无法回答的问题的公开信号。",
        "caveat_en": "It is trained on photographic aesthetics and can penalize deliberately painterly, ink-wash, or stylized textures. Never use it as a style-transfer score on its own.",
        "caveat_zh": "该预测器基于摄影美学训练，可能惩罚刻意为之的绘画、水墨或强风格化纹理。绝不能单独把它当作风格迁移分数。",
    },
    {
        "id": "vbench_imaging_quality",
        "name_en": "VBench imaging quality",
        "name_zh": "VBench 成像质量",
        "available_keys": ["vbench_imaging_quality"],
        "formula": "Imaging = (1/T) * sum_t MUSIQ(I_t)",
        "formula_tex": r"\mathrm{Imaging}=\frac{1}{T}\sum_{t=1}^{T}\mathrm{MUSIQ}(I_t)",
        "rationale_en": "MUSIQ is a no-reference image-quality model, so it can flag compression, blur, and noise artifacts without a ground-truth target. EchoStyle reports this column as 'Imaging Qual.'",
        "rationale_zh": "MUSIQ 是无参考图像质量模型，无需真值即可标记压缩、模糊与噪声伪影。EchoStyle 将其作为“Imaging Qual.”列报告。",
        "caveat_en": "No-reference quality models can reward oversharpening and may score a heavily textured painting style lower than a clean photo. Report the model version and input resolution.",
        "caveat_zh": "无参考质量模型可能奖励过度锐化，并给纹理强烈的绘画风格打更低的分。必须报告模型版本与输入分辨率。",
    },
]


METRIC_DIMENSION_LABELS = {
    "en": {
        "style": "Style",
        "content": "Content",
        "temporal": "Temporal",
        "motion": "Motion",
        "quality": "Video quality",
        "cost": "Cost",
    },
    "zh": {
        "style": "风格",
        "content": "内容",
        "temporal": "时序",
        "motion": "运动",
        "quality": "视频质量",
        "cost": "成本",
    },
}


def metrics_at_a_glance_rows(
    metrics: dict[str, Any],
    lang: str,
) -> list[dict[str, str]]:
    """Compact one-screen summary of the metrics present in this run."""
    info_by_metric = metrics.get("metric_info", {})
    rows = []
    for metric, _ in KEY_METRICS:
        info = info_by_metric.get(metric)
        if not info:
            continue
        dimension = info.get("dimension")
        rows.append(
            {
                "id": metric,
                "label": metric_label(lang, metric, info),
                "dimension": METRIC_DIMENSION_LABELS[lang].get(dimension, dimension or "—"),
                "direction": "↑" if info.get("higher_is_better") else "↓",
                "unit": info.get("unit") or "—",
            }
        )
    return rows


#: Metric families used for the executive dashboard, in display order.
KEY_RESULT_FAMILIES = (
    ("style", ("csd_s", "clip_i", "lab_palette_w1")),
    ("content", ("ssim", "psnr", "lpips", "clip_f")),
    ("temporal", ("offset_1_warp_rmse", "luminance_flicker")),
    ("quality", ("vbench_aesthetic_quality", "vbench_imaging_quality")),
    ("cost", ("runtime_s", "peak_memory_gb")),
)

#: EchoStyle Table 1 parity checklist: (label, candidate metric ids, proxy?).
ECHOSTYLE_COVERAGE = (
    ("Style Similarity", ("vlm_style_pref",), False),
    ("Style consistency", ("csd_s",), False),
    ("Motion smoothness", ("vbench_motion_smoothness",), False),
    ("Imaging quality", ("vbench_imaging_quality",), False),
    ("Aesthetic quality", ("vbench_aesthetic_quality",), False),
    (
        "Static quality",
        ("vbench_subject_consistency", "vbench_background_consistency"),
        True,
    ),
    ("Dynamic quality", ("vbench_dynamic_degree",), True),
)


def key_result_rows(
    metrics: dict[str, Any],
    primary: str | None,
    baseline: str | None,
    lang: str,
) -> list[dict[str, Any]]:
    """One row per evidence family: the headline metric and its paired delta."""
    aggregates = metrics.get("aggregates", {})
    info_by_metric = metrics.get("metric_info", {})
    if not primary:
        methods = metrics.get("methods", [])
        primary = methods[0]["id"] if methods else None
    rows = []
    for dimension, candidates in KEY_RESULT_FAMILIES:
        metric = next(
            (
                candidate
                for candidate in candidates
                if candidate in info_by_metric
                and aggregates.get(primary or "", {}).get(candidate)
                and aggregates[primary or ""][candidate].get("mean") is not None
            ),
            None,
        )
        if metric is None:
            continue
        info = info_by_metric[metric]
        primary_summary = aggregates[primary][metric]
        baseline_summary = (
            aggregates.get(baseline or "", {}).get(metric) if baseline else None
        )
        delta = None
        if (
            baseline_summary
            and baseline_summary.get("mean") is not None
            and primary_summary.get("mean") is not None
        ):
            raw = primary_summary["mean"] - baseline_summary["mean"]
            delta = raw if info.get("higher_is_better") else -raw
        method_order = [m["id"] for m in metrics.get("methods", [])]
        values = {
            method_id: stat_without_n(aggregates.get(method_id, {}).get(metric))
            for method_id in method_order
        }
        numeric = [
            (method_id, aggregates[method_id][metric]["mean"])
            for method_id in method_order
            if aggregates.get(method_id, {}).get(metric)
            and aggregates[method_id][metric].get("mean") is not None
        ]
        numeric.sort(key=lambda item: item[1], reverse=bool(info.get("higher_is_better")))
        best_ids = [mid for mid, value in numeric[:1]]
        second_ids = (
            [mid for mid, value in numeric[1:2]] if len(numeric) > 1 else []
        )
        rows.append(
            {
                "dimension": METRIC_DIMENSION_LABELS[lang].get(dimension, dimension),
                "metric": metric_label(lang, metric, info),
                "metric_id": metric,
                "values": values,
                "method_ids": method_order,
                "best_ids": best_ids,
                "second_ids": second_ids,
                "primary": stat_without_n(primary_summary),
                "baseline": (
                    stat_without_n(baseline_summary) if baseline_summary else "—"
                ),
                "delta": delta,
                "higher_is_better": bool(info.get("higher_is_better")),
                "bar": relative_bar(
                    primary_summary.get("mean"),
                    baseline_summary.get("mean") if baseline_summary else None,
                ),
            }
        )
    return rows


def coverage_rows(
    metrics: dict[str, Any],
    lang: str,
) -> list[dict[str, str]]:
    """EchoStyle Table 1 parity: present, proxy or missing for each column."""
    info_by_metric = metrics.get("metric_info", {})
    rows = []
    for label, candidates, proxy in ECHOSTYLE_COVERAGE:
        present = [candidate for candidate in candidates if candidate in info_by_metric]
        if present:
            status = "proxy" if proxy else "present"
            evidence = ", ".join(
                metric_label(lang, candidate, info_by_metric[candidate])
                for candidate in present
            )
        else:
            status = "missing"
            evidence = (
                "Gemini pairwise judge (not configured)"
                if label == "Style Similarity"
                else "—"
            )
        rows.append({"label": label, "status": status, "evidence": evidence})
    return rows


def metric_family_counts(metrics: dict[str, Any]) -> list[tuple[str, int]]:
    """Count registered metrics per dimension for the coverage summary."""
    counts: dict[str, int] = {}
    for meta in metrics.get("metric_info", {}).values():
        dimension = meta.get("dimension") or "other"
        counts[dimension] = counts.get(dimension, 0) + 1
    order = ("style", "content", "temporal", "motion", "quality", "cost")
    return [(dimension, counts[dimension]) for dimension in order if dimension in counts]


def glance_by_family(
    metrics: dict[str, Any],
    lang: str,
) -> list[tuple[str, list[dict[str, str]]]]:
    """Group the at-a-glance rows by evidence family, in canonical order."""
    groups: dict[str, list[dict[str, str]]] = {}
    for row in metrics_at_a_glance_rows(metrics, lang):
        groups.setdefault(row["dimension"], []).append(row)
    order = [
        METRIC_DIMENSION_LABELS[lang][dimension]
        for dimension in ("style", "content", "temporal", "motion", "quality", "cost")
    ]
    return [(name, groups[name]) for name in order if name in groups]


def relative_bar(value: float | None, reference: float | None, width: int = 8) -> str:
    """Unicode bar for text-only formats; proportional to the larger of the two."""
    if value is None:
        return ""
    scale = max(abs(value), abs(reference or 0.0), 1e-9)
    filled = max(1, int(round(abs(value) / scale * width)))
    return "█" * filled + "·" * (width - filled)


def data_profile_rows(
    metrics: dict[str, Any],
    lang: str,
) -> list[tuple[str, str]]:
    s = TEXT[lang]
    experiment = metrics.get("experiment", {})
    cases = metrics.get("cases", [])
    contents = {case.get("content_id") for case in cases if case.get("content_id")}
    styles = {case.get("style_id") for case in cases if case.get("style_id")}
    splits = {str(case.get("split")) for case in cases if case.get("split")}
    durations = [
        float(case["source_metadata"]["duration_s"])
        for case in cases
        if isinstance(case.get("source_metadata"), dict)
        and case["source_metadata"].get("duration_s")
    ]
    resolutions = {
        f"{case['source_metadata']['width']}x{case['source_metadata']['height']}"
        for case in cases
        if isinstance(case.get("source_metadata"), dict)
        and case["source_metadata"].get("width")
    }
    warnings = sum(len(case.get("warnings", [])) for case in cases)
    source = str(experiment.get("data_source") or experiment.get("notes") or "example")
    return [
        (s["data_count"], str(len(cases))),
        (s["data_source"], source[:160]),
        (s["content_count"], str(len(contents))),
        (s["style_count"], str(len(styles))),
        (
            s["mean_duration"],
            f"{sum(durations) / len(durations):.2f} s" if durations else "—",
        ),
        (s["resolutions"], ", ".join(sorted(resolutions)) or "—"),
    ]


QUALITATIVE_DEFINITIONS = (
    {
        "id": "style_adherence",
        "name_en": "Style adherence (VLM)",
        "name_zh": "风格遵循（VLM）",
        "formula": "score in 1-5 from the blinded contact-sheet rubric",
        "rationale_en": "The judge sees the style reference, source frames and blinded candidate rows in one contact sheet, then scores how well each candidate follows the requested style. The prompt is fixed and recorded with the review export.",
        "rationale_zh": "评审模型在同一张 contact sheet 上看到风格参考、源帧和盲化候选行，然后对每个候选的风格遵循程度打 1-5 分；提示词固定并随评审记录保存。",
        "caveat_en": "Subjective: record the judge model, prompt version and reviewer count; do not compare across different judges.",
        "caveat_zh": "主观指标：必须记录评审模型、提示词版本和评审次数，不同评审模型之间不可直接比较。",
    },
    {
        "id": "content_preservation",
        "name_en": "Content preservation (VLM)",
        "name_zh": "内容保持（VLM）",
        "formula": "score in 1-5 from the blinded contact-sheet rubric",
        "rationale_en": "Scores whether the subject, layout and scene semantics survive stylization, using the source frames as the reference.",
        "rationale_zh": "以源帧为参照，评估主体、构图与场景语义在风格化后是否保留。",
        "caveat_en": "Image-level judgement; local identity or occlusion errors need the per-case evidence.",
        "caveat_zh": "图像级判断；局部身份或遮挡错误仍需逐案例证据。",
    },
    {
        "id": "temporal_stability",
        "name_en": "Temporal stability (VLM)",
        "name_zh": "时序稳定性（VLM）",
        "formula": "score in 1-5 from the blinded contact-sheet rubric",
        "rationale_en": "Scores flicker, jitter and temporal coherence visible across the sampled frames.",
        "rationale_zh": "根据采样帧之间的闪烁、抖动与时序连贯性打分。",
        "caveat_en": "Contact sheets sample frames; subtle high-frequency flicker can be missed.",
        "caveat_zh": "contact sheet 只采样部分帧，细微高频闪烁可能被漏掉。",
    },
    {
        "id": "artifact_control",
        "name_en": "Artifact control (VLM)",
        "name_zh": "伪影控制（VLM）",
        "formula": "score in 1-5 from the blinded contact-sheet rubric",
        "rationale_en": "Scores visible artifacts such as texture sticking, ghosting, banding and geometric distortion.",
        "rationale_zh": "对纹理粘连、重影、色带与几何畸变等可见伪影打分。",
        "caveat_en": "Artifact severity depends on display size; review at the reported resolution.",
        "caveat_zh": "伪影严重程度与显示尺寸有关，应在报告分辨率下查看。",
    },
    {
        "id": "overall_visual_quality",
        "name_en": "Overall visual quality (VLM)",
        "name_zh": "整体视觉质量（VLM）",
        "formula": "score in 1-5 from the blinded contact-sheet rubric",
        "rationale_en": "A holistic preference score combining style, content and temporal impression.",
        "rationale_zh": "综合风格、内容与时序印象的整体偏好分。",
        "caveat_en": "Do not collapse it into a benchmark claim without per-dimension evidence.",
        "caveat_zh": "没有各维度证据时，不能把它单独当作基准结论。",
    },
)


def metric_button(metric_id: str, label: str, lang: str) -> str:
    definition = next(
        (
            item
            for item in METRIC_DEFINITIONS
            if item["id"] == metric_id
            or metric_id in item.get("available_keys", [])
        ),
        None,
    )
    if definition is None:
        definition = next(
            (item for item in QUALITATIVE_DEFINITIONS if item["id"] == metric_id),
            None,
        )
    if definition is None:
        return html.escape(label)
    return (
        f"<button class='metric-link' data-name='{html.escape(label, quote=True)}' "
        f"data-formula='{html.escape(definition.get('formula_tex') or definition['formula'], quote=True)}' "
        f"data-why='{html.escape(definition[f'rationale_{lang}'], quote=True)}' "
        f"data-caveat='{html.escape(definition[f'caveat_{lang}'], quote=True)}'>"
        f"{html.escape(label)}</button>"
    )


def metric_definition_rows(
    metrics: dict[str, Any],
    lang: str,
) -> list[dict[str, str]]:
    aggregates = metrics.get("aggregates", {})
    available_keys = set()
    for method_summary in aggregates.values():
        available_keys.update(method_summary.keys())
    rows = []
    for definition in METRIC_DEFINITIONS:
        keys = definition.get("available_keys", [])
        if definition["id"] == "vlm":
            available = True
        else:
            available = any(key in available_keys for key in keys)
        rows.append(
            {
                "name": definition[f"name_{lang}"],
                "formula": definition["formula"],
                "formula_tex": definition["formula_tex"],
                "rationale": definition[f"rationale_{lang}"],
                "caveat": definition[f"caveat_{lang}"],
                "available": (
                    "在本次运行中计算" if lang == "zh" else "Computed in this run"
                )
                if available
                else (
                    "本次运行未提供；定义用于论文级扩展"
                    if lang == "zh"
                    else "Not provided in this run; definition retained for paper-grade extension"
                ),
                "available_bool": available,
            }
        )
    return rows


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
    parser.add_argument(
        "--report-datetime",
        default=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        help="Timestamp shown in the header, precise to the second.",
    )
    parser.add_argument("--report-id", help="Override the generated report ID.")
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="Extra note shown in the Notes section below the conclusion.",
    )
    parser.add_argument(
        "--note-zh",
        action="append",
        default=[],
        help="Chinese variant of --note; used when the report language is zh.",
    )
    parser.add_argument(
        "--skill-url",
        default="https://github.com/0x0addc001/video-style-transfer-eval",
        help="Skill repository linked from the report header.",
    )
    parser.add_argument(
        "--pdf-engine",
        choices=("chrome", "reportlab"),
        default="chrome",
        help="Use headless Chrome to print the HTML report, or ReportLab.",
    )
    parser.add_argument(
        "--chrome-path",
        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        help="Chrome/Chromium binary for --pdf-engine chrome.",
    )
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


def asset_name(value: Any) -> str:
    """Basename of a contact-sheet path, tolerating Windows-authored metrics."""
    return Path(str(value).replace("\\", "/")).name


def resolve_asset_source(value: Any, metrics_dir: Path) -> Path:
    """Resolve a contact-sheet path, accepting relative and Windows-style input."""
    normalized = Path(str(value).replace("\\", "/"))
    return normalized if normalized.is_absolute() else metrics_dir / normalized


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
            "models": [],
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

    models = sorted(
        {
            str(item.get("reviewer", {}).get("model"))
            for item in review.get("reviews", [])
            if item.get("reviewer", {}).get("model")
        }
    )
    return {
        "reviewer_count": review.get("reviewer_count", len(review.get("reviews", []))),
        "scored_count": scored_count,
        "method_dimension": method_dimension,
        "failure_counts": failure_counts,
        "preference_counts": preference_counts,
        "per_case": dict(per_case),
        "models": models,
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
            "csd_s",
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
                    f"定性评估（VLM）：{labels.get(best_method, best_method)}的整体视觉质量"
                    f"均值最高（{best_score:.2f}/5，"
                    f"{review_agg['reviewer_count']} 位审查者）；这是感知证据，不是基准真值。"
                )
            else:
                findings.append(
                    f"Qualitative assessment (VLM): {labels.get(best_method, best_method)} has "
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
            "当前没有定性评估（VLM）记录，因此不给出感知质量结论。"
            if lang == "zh"
            else "Qualitative assessment (VLM) is absent, so no perceptual quality conclusion is made."
        )
    if primary:
        vbench_values = []
        for metric in (
            "vbench_motion_smoothness",
            "vbench_aesthetic_quality",
            "vbench_imaging_quality",
        ):
            summary = metrics.get("aggregates", {}).get(primary, {}).get(metric)
            if metric in metrics.get("metric_info", {}) and summary:
                vbench_values.append(
                    f"{metric_label(lang, metric, metrics['metric_info'][metric])} "
                    f"{stat_without_n(summary)}"
                )
        if vbench_values:
            method_label = labels.get(primary, primary)
            findings.append(
                (
                    f"VBench 视频质量（{method_label}）："
                    + "；".join(vbench_values)
                    + "。这些分数在 custom_input 模式下计算，不能与 VBench 官方榜单直接比较。"
                )
                if lang == "zh"
                else (
                    f"VBench video quality for {method_label}: "
                    + "; ".join(vbench_values)
                    + ". These scores use VBench custom_input mode and are not "
                    "leaderboard-comparable."
                )
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
        if any(
            metric in method_aggregate
            for metric in (
                "lpips",
                "clip_i",
                "clip_f",
                "fid",
                "artfid",
                "csd_s",
                "csd_c",
                "vbench_motion_smoothness",
                "vbench_aesthetic_quality",
                "vbench_imaging_quality",
            )
        ):
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
                "不要把这次探索性运行作为模型性能证据。"
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
            ("视频质量", "quality"),
            ("计算成本", "cost"),
        ]
        if lang == "zh"
        else [
            ("Style", "style"),
            ("Content", "content"),
            ("Temporal and motion", "temporal"),
            ("Video quality", "quality"),
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
        for metric, _, info in selected:
            summaries = {
                method_id: metrics.get("aggregates", {})
                .get(method_id, {})
                .get(metric)
                for method_id in method_order
            }
            available = [
                (method_id, float(summary["mean"]))
                for method_id, summary in summaries.items()
                if summary and summary.get("mean") is not None
            ]
            higher = bool(info.get("higher_is_better"))
            available.sort(key=lambda item: item[1], reverse=higher)
            distinct_values = sorted(
                {round(value, 12) for _, value in available},
                reverse=higher,
            )
            best_value = distinct_values[0] if distinct_values else None
            second_value = distinct_values[1] if len(distinct_values) > 1 else None
            best_ids = [
                method_id
                for method_id, value in available
                if best_value is not None and abs(value - best_value) < 1e-12
            ]
            second_ids = [
                method_id
                for method_id, value in available
                if second_value is not None and abs(value - second_value) < 1e-12
            ]
            label = metric_label(lang, metric, info)
            unit = info.get("unit")
            if unit:
                label = f"{label} ({unit})"
            rows.append(
                {
                    "metric": metric,
                    "label": label,
                    "higher_is_better": higher,
                    "summaries": summaries,
                    "best_ids": best_ids,
                    "second_ids": second_ids,
                }
            )
        tables.append(
            {
                "heading": heading,
                "headers": [tr(lang, "metric")]
                + [labels.get(method_id, method_id) for method_id in method_order],
                "method_ids": method_order,
                "rows": rows,
            }
        )
    return tables


def stat_without_n(summary: dict[str, Any] | None, digits: int = 4) -> str:
    if not summary:
        return "—"
    return (
        f"{format_number(summary.get('mean'), digits)} ± "
        f"{format_number(summary.get('std'), digits)}"
    )


def table_sample_note(table: dict[str, Any]) -> str:
    notes = []
    for method_id in table["method_ids"]:
        n_values = {
            row["summaries"].get(method_id, {}).get("n")
            for row in table["rows"]
            if row["summaries"].get(method_id)
        }
        n_text = ", ".join(str(value) for value in sorted(n_values) if value is not None)
        if n_text:
            notes.append(f"{method_id}: {n_text}")
    return "; ".join(notes)


def comparison_vote(
    metrics: dict[str, Any],
    primary: str,
    baseline: str,
    metric: str,
) -> int:
    info = metrics.get("metric_info", {}).get(metric, {})
    primary_summary = metrics.get("aggregates", {}).get(primary, {}).get(metric)
    baseline_summary = metrics.get("aggregates", {}).get(baseline, {}).get(metric)
    if not primary_summary or not baseline_summary:
        return 0
    difference = float(primary_summary["mean"]) - float(baseline_summary["mean"])
    if abs(difference) < 1e-12:
        return 0
    return 1 if (difference > 0) == bool(info.get("higher_is_better")) else -1


def review_vote(
    review_agg: dict[str, Any],
    primary: str,
    baseline: str,
    dimension: str,
) -> int:
    primary_value = (
        review_agg.get("method_dimension", {})
        .get(primary, {})
        .get(dimension, {})
        .get("mean")
    )
    baseline_value = (
        review_agg.get("method_dimension", {})
        .get(baseline, {})
        .get(dimension, {})
        .get("mean")
    )
    if primary_value is None or baseline_value is None:
        return 0
    difference = float(primary_value) - float(baseline_value)
    if abs(difference) < 1e-12:
        return 0
    return 1 if difference > 0 else -1


def category_verdict(votes: list[int], primary_name: str, baseline_name: str, lang: str) -> str:
    available = [vote for vote in votes if vote != 0]
    if not available:
        return (
            "现有证据不足以判断差异。"
            if lang == "zh"
            else "The available evidence is insufficient to distinguish the methods."
        )
    score = sum(available)
    if score > 0:
        return (
            f"现有指标总体上更支持 {primary_name}。"
            if lang == "zh"
            else f"The available indicators collectively favor {primary_name}."
        )
    if score < 0:
        return (
            f"现有指标总体上更支持 {baseline_name}。"
            if lang == "zh"
            else f"The available indicators collectively favor {baseline_name}."
        )
    return (
        "现有指标意见不一致或方向抵消。"
        if lang == "zh"
        else "The available indicators disagree or cancel in aggregate."
    )


def make_analysis_sections(
    metrics: dict[str, Any],
    labels: dict[str, str],
    review_agg: dict[str, Any],
    primary: str | None,
    baseline: str | None,
    lang: str,
) -> list[dict[str, str]]:
    if not primary or not baseline or primary not in labels or baseline not in labels:
        return []
    s = TEXT[lang]
    primary_name = labels[primary]
    baseline_name = labels[baseline]
    aggregates = metrics.get("aggregates", {})

    style_metrics = ["clip_i", "csd_s", "lab_palette_w1", "lab_ab_palette_w1"]
    style_votes = [
        comparison_vote(metrics, primary, baseline, metric)
        for metric in style_metrics
        if metric in metrics.get("metric_info", {})
    ]
    style_votes.append(
        review_vote(review_agg, primary, baseline, "style_adherence")
    )
    style_values = []
    for metric in style_metrics:
        summary = aggregates.get(primary, {}).get(metric)
        if summary:
            info = metrics["metric_info"][metric]
            style_values.append(
                f"{metric_label(lang, metric, info)} "
                f"{stat_without_n(summary)}"
            )
    style_review = (
        review_agg.get("method_dimension", {})
        .get(primary, {})
        .get("style_adherence", {})
        .get("mean")
    )
    style_text = category_verdict(style_votes, primary_name, baseline_name, lang)
    if style_values:
        style_text += (
            " 已报告的诊断值为："
            + "；".join(style_values)
            + "。"
            if lang == "zh"
            else " Reported diagnostics: "
            + "; ".join(style_values)
            + "."
        )
    if style_review is not None:
        style_text += (
            f" 盲评风格一致性为 {style_review:.2f}/5。"
            if lang == "zh"
            else f" The blinded style-adherence score is {style_review:.2f}/5."
        )

    content_metrics = ["lpips", "clip_f", "csd_c", "ssim", "psnr"]
    content_votes = [
        comparison_vote(metrics, primary, baseline, metric)
        for metric in content_metrics
        if metric in metrics.get("metric_info", {})
    ]
    content_votes.append(
        review_vote(review_agg, primary, baseline, "content_preservation")
    )
    content_values = []
    for metric in content_metrics:
        summary = aggregates.get(primary, {}).get(metric)
        if summary:
            info = metrics["metric_info"][metric]
            content_values.append(
                f"{metric_label(lang, metric, info)} "
                f"{stat_without_n(summary)}"
            )
    content_text = category_verdict(
        content_votes, primary_name, baseline_name, lang
    )
    if content_values:
        content_text += (
            " 已报告的诊断值为："
            + "；".join(content_values)
            + "。"
            if lang == "zh"
            else " Reported diagnostics: "
            + "; ".join(content_values)
            + "."
        )

    temporal_metric_candidates = [
        "offset_1_warp_rmse",
        "offset_5_warp_rmse",
        "offset_1_flow_epe",
        "luminance_flicker",
        "tlp",
        "clip_cons",
        "vbench_subject_consistency",
        "vbench_background_consistency",
        "vbench_temporal_flickering",
        "vbench_motion_smoothness",
    ]
    temporal_metrics = [
        metric
        for metric in temporal_metric_candidates
        if metric in metrics.get("metric_info", {})
    ]
    temporal_votes = [
        comparison_vote(metrics, primary, baseline, metric)
        for metric in temporal_metrics
    ]
    temporal_votes.append(
        review_vote(review_agg, primary, baseline, "temporal_stability")
    )
    temporal_values = []
    for metric in temporal_metrics:
        summary = aggregates.get(primary, {}).get(metric)
        if summary:
            info = metrics["metric_info"][metric]
            temporal_values.append(
                f"{metric_label(lang, metric, info)} "
                f"{stat_without_n(summary)}"
            )
    temporal_text = category_verdict(
        temporal_votes, primary_name, baseline_name, lang
    )
    if temporal_values:
        temporal_text += (
            " 已报告的诊断值为："
            + "；".join(temporal_values)
            + "。"
            if lang == "zh"
            else " Reported diagnostics: "
            + "; ".join(temporal_values)
            + "."
        )

    quality_metrics = [
        metric
        for metric in ("vbench_aesthetic_quality", "vbench_imaging_quality")
        if metric in metrics.get("metric_info", {})
    ]
    quality_votes = [
        comparison_vote(metrics, primary, baseline, metric)
        for metric in quality_metrics
    ]
    quality_values = []
    for metric in quality_metrics:
        summary = aggregates.get(primary, {}).get(metric)
        if summary:
            info = metrics["metric_info"][metric]
            quality_values.append(
                f"{metric_label(lang, metric, info)} "
                f"{stat_without_n(summary)}"
            )
    quality_text = category_verdict(
        quality_votes, primary_name, baseline_name, lang
    )
    if quality_values:
        quality_text += (
            " 已报告的视频质量指标为："
            + "；".join(quality_values)
            + "。"
            if lang == "zh"
            else " Reported video-quality metrics: "
            + "; ".join(quality_values)
            + "."
        )

    perceptual_text = (
        "当前没有经过校验的盲评记录，因此不将伪影或文本纹理质量纳入模型优劣判断。"
        if lang == "zh"
        else "No validated blinded review is available, so artifact and texture quality are not used to rank the methods."
    )
    if review_agg.get("scored_count"):
        best_method = max(
            review_agg["method_dimension"],
            key=lambda method_id: (
                review_agg["method_dimension"][method_id][
                    "overall_visual_quality"
                ]["mean"]
                if review_agg["method_dimension"][method_id][
                    "overall_visual_quality"
                ]["mean"]
                is not None
                else -1
            ),
        )
        best_score = review_agg["method_dimension"][best_method][
            "overall_visual_quality"
        ]["mean"]
        top_tags = review_agg["failure_counts"].most_common(3)
        if lang == "zh":
            perceptual_text = (
                f"盲评中整体视觉质量最高的是 {labels.get(best_method, best_method)}"
                f"（{best_score:.2f}/5，{review_agg['reviewer_count']} 位审查者）。"
                "该结果仅代表当前审查样本中的感知偏好，不等同于真实标签。"
            )
            if top_tags:
                perceptual_text += " 主要失败模式为" + "、".join(
                    f"{FAILURE_LABELS['zh'].get(tag, tag)}（{count}）"
                    for tag, count in top_tags
                ) + "。"
        else:
            perceptual_text = (
                f"The blinded review gives the highest overall visual quality to "
                f"{labels.get(best_method, best_method)} ({best_score:.2f}/5 across "
                f"{review_agg['reviewer_count']} reviewer(s)). This reflects preference "
                "on the reviewed sample rather than ground-truth quality."
            )
            if top_tags:
                perceptual_text += " The leading failure modes are " + ", ".join(
                    f"{tag.replace('_', ' ')} ({count})"
                    for tag, count in top_tags
                ) + "."

    cost_votes = [
        comparison_vote(metrics, primary, baseline, metric)
        for metric in ("runtime_s", "peak_memory_gb")
        if metric in metrics.get("metric_info", {})
    ]
    cost_text = category_verdict(cost_votes, primary_name, baseline_name, lang)
    if lang == "zh":
        runtime = aggregates.get(primary, {}).get("runtime_s")
        memory = aggregates.get(primary, {}).get("peak_memory_gb")
        details = []
        if runtime:
            details.append(f"运行时间 {stat_without_n(runtime)} 秒")
        if memory:
            details.append(f"峰值显存 {stat_without_n(memory)} GB")
        if details:
            cost_text += " 主方法的" + "、".join(details) + "。"
    else:
        runtime = aggregates.get(primary, {}).get("runtime_s")
        memory = aggregates.get(primary, {}).get("peak_memory_gb")
        details = []
        if runtime:
            details.append(f"runtime {stat_without_n(runtime)} s")
        if memory:
            details.append(f"peak memory {stat_without_n(memory)} GB")
        if details:
            cost_text += " The primary method uses " + " and ".join(details) + "."

    category_votes = [
        sum(style_votes),
        sum(content_votes),
        sum(temporal_votes),
        sum(quality_votes),
        sum(cost_votes),
    ]
    wins = sum(vote > 0 for vote in category_votes)
    losses = sum(vote < 0 for vote in category_votes)
    if wins >= 3 and losses == 0:
        synthesis_text = (
            f"在可用指标上，{primary_name} 在多数评估维度中占优，但不同维度和样本间仍存在差异。"
            if lang == "zh"
            else f"Across the available evidence, {primary_name} has an advantage in most dimensions, although variation remains across cases."
        )
    elif losses >= 3 and wins == 0:
        synthesis_text = (
            f"在可用指标上，{baseline_name} 在多数评估维度中占优。"
            if lang == "zh"
            else f"Across the available evidence, {baseline_name} has an advantage in most dimensions."
        )
    else:
        synthesis_text = (
            "结果呈现明显的多维权衡，没有方法在所有维度上占优；因此不能据此声称单一方法的普遍优越性。"
            if lang == "zh"
            else "The results show a multidimensional trade-off rather than universal dominance; the current evidence does not support a claim that one method is uniformly superior."
        )

    sections = [
        {"heading": s["style_analysis"], "text": style_text},
        {"heading": s["content_analysis"], "text": content_text},
        {"heading": s["temporal_analysis"], "text": temporal_text},
    ]
    if quality_metrics:
        sections.append({"heading": s["quality_analysis"], "text": quality_text})
    sections.extend(
        [
            {"heading": s["perceptual_analysis"], "text": perceptual_text},
            {"heading": s["cost_analysis"], "text": cost_text},
            {"heading": s["synthesis"], "text": synthesis_text},
        ]
    )
    return sections


def make_conclusion(
    metrics: dict[str, Any],
    labels: dict[str, str],
    review_agg: dict[str, Any],
    primary: str | None,
    baseline: str | None,
    status: str,
    lang: str,
) -> str:
    valid_cases = sum(
        1
        for case in metrics.get("cases", [])
        if any(result.get("valid") for result in case.get("methods", {}).values())
    )
    if lang == "zh":
        if status == "Exploratory":
            return (
                f"本报告用 {valid_cases} 个案例验证了评估流程，未提供基准性能证据。"
                "结果表、感知分析和结论仍保留多维证据，不应被解释为 EchoStyle 或本文方法的基准排名。"
            )
        suffix = (
            "由于独立片段数量少于五个，当前差异未配套稳定置信区间，应视为探索性比较。"
            if valid_cases < 5
            else "应结合配对差值的置信区间判断差异稳定性和实际意义。"
        )
        return (
            "评估显示风格、内容、运动、视频质量与成本目标之间可能存在权衡；"
            "只有在替代方案取得相近风格强度后才可解释保持性差异。"
            + suffix
        )
    if status == "Exploratory":
        return (
            f"This report uses {valid_cases} case(s) to validate the evaluation "
            "pipeline and does not provide benchmark performance evidence. The "
            "tables, perceptual analysis, and conclusions preserve multidimensional "
            "evidence and should not be interpreted as a benchmark ranking of EchoStyle "
            "or the proposed method."
        )
    suffix = (
        "With fewer than five independent clips, the observed differences lack stable "
        "confidence intervals and should be treated as exploratory."
        if valid_cases < 5
        else "Paired confidence intervals should be used to judge the stability and practical relevance of the differences."
    )
    return (
        "The evaluation indicates that style, content, motion, video quality, and cost "
        "objectives may trade off. Preservation differences are interpretable only "
        "after methods are compared at similar achieved style strength. "
        + suffix
    )


def paired_effect_rows(
    metrics: dict[str, Any],
    primary: str,
    baseline: str,
    labels: dict[str, str],
    lang: str,
) -> list[dict[str, Any]]:
    rows = []
    for metric in (
        "ssim",
        "lab_palette_w1",
        "csd_s",
        "csd_c",
        "offset_1_warp_rmse",
        "offset_1_flow_epe",
        "vbench_motion_smoothness",
        "vbench_aesthetic_quality",
        "vbench_imaging_quality",
        "runtime_s",
    ):
        info = metrics.get("metric_info", {}).get(metric)
        if not info:
            continue
        raw_differences = []
        for case in metrics.get("cases", []):
            first = case.get("methods", {}).get(primary)
            second = case.get("methods", {}).get(baseline)
            if not first or not second or not first.get("valid") or not second.get("valid"):
                continue
            first_value = first.get("metrics", {}).get(metric)
            second_value = second.get("metrics", {}).get(metric)
            if first_value is None or second_value is None:
                continue
            difference = float(first_value) - float(second_value)
            raw_differences.append(
                difference if info.get("higher_is_better") else -difference
            )
        if not raw_differences:
            continue
        mean_difference = float(np.mean(raw_differences))
        std_difference = (
            float(np.std(raw_differences, ddof=1))
            if len(raw_differences) > 1
            else 0.0
        )
        effect_size = (
            mean_difference / std_difference if std_difference > 1e-12 else None
        )
        paired = get_pairwise(metrics, primary, baseline, metric)
        rows.append(
            {
                "metric": metric,
                "label": metric_label(lang, metric, info),
                "higher_is_better": bool(info.get("higher_is_better")),
                "n": len(raw_differences),
                "mean_difference_favors_primary": mean_difference,
                "effect_size_dz": effect_size,
                "ci": paired.get("ci95_diff") if paired else None,
                "primary_label": labels.get(primary, primary),
                "baseline_label": labels.get(baseline, baseline),
            }
        )
    return rows


def configuration_rows(
    metrics: dict[str, Any],
    labels: dict[str, str],
    lang: str,
    evidence_path: str,
    review_agg: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    """Reproducibility and test-design details shown in the config table."""
    s = TEXT[lang]
    experiment = metrics.get("experiment", {})
    methods = [
        labels.get(method.get("id"), method.get("id"))
        for method in metrics.get("methods", [])
    ]
    flow = str(experiment.get("flow_implementation", "—")).replace(
        " (diagnostic proxy)", ""
    )
    rows: list[tuple[str, str]] = [
        (s["methods_list"], ", ".join(methods)),
        (s["seed"], str(experiment.get("blind_seed", experiment.get("seed", "—")))),
        (s["sample_frames"], str(experiment.get("frame_limit", "—"))),
        (s["max_side"], f"{experiment.get('max_side', '—')} px"),
        (s["temporal_offsets"], str(experiment.get("temporal_offsets", "—"))),
        (s["flow_implementation"], str(flow)),
    ]
    models = (review_agg or {}).get("models") or []
    if models:
        rows.append((s["review_model"], ", ".join(models)))
    return rows


def metric_classification_rows(
    metrics: dict[str, Any],
    lang: str,
) -> list[tuple[str, str]]:
    return [
        (family, ", ".join(row["label"] for row in family_rows))
        for family, family_rows in glance_by_family(metrics, lang)
    ]


def repo_name_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1] or url


def report_notes(args: argparse.Namespace, lang: str) -> list[str]:
    zh_notes = getattr(args, "note_zh", None)
    if lang == "zh" and zh_notes:
        return list(zh_notes)
    return list(getattr(args, "note", []) or [])


def report_identity(args: argparse.Namespace, metrics: dict[str, Any]) -> tuple[str, str]:
    """Report ID derived from the timestamp and the manifest evidence hash."""
    evidence = str(metrics.get("manifest_sha256") or "unknown")
    stamp = (
        str(getattr(args, "report_datetime", ""))
        .replace("-", "")
        .replace(":", "")
        .replace(" ", "T")
    )
    return (
        getattr(args, "report_id", None) or f"VST-{stamp}-{evidence[:12]}",
        evidence,
    )


def run_scope_line(
    metrics: dict[str, Any],
    review_agg: dict[str, Any],
    lang: str,
) -> str:
    s = TEXT[lang]
    return " · ".join(
        [
            f"{s['methods_count']}: {len(metrics.get('methods', []))}",
            f"{s['cases_count']}: {len(metrics.get('cases', []))}",
            f"{s['metrics_count']}: {len(metrics.get('metric_info', {}))}",
            f"{s['reviewers_count']}: {review_agg.get('reviewer_count', 0)}",
        ]
    )


def family_comment(
    metrics: dict[str, Any],
    labels: dict[str, str],
    primary: str | None,
    baseline: str | None,
    table: dict[str, Any],
    lang: str,
) -> str:
    """One-sentence comment attached under a results table."""
    if not primary or not baseline:
        return ""
    for row in table.get("rows", []):
        metric = row.get("metric")
        if metric and metric in metrics.get("metric_info", {}):
            return comparison_phrase(
                metrics, labels, primary, baseline, metric, lang
            )
    return ""


def markdown_report(
    metrics: dict[str, Any],
    labels: dict[str, str],
    review_agg: dict[str, Any],
    status: str,
    findings: list[str],
    recommendation: str,
    analysis_sections: list[dict[str, str]],
    conclusion: str,
    paired_rows: list[dict[str, Any]],
    args: argparse.Namespace,
    lang: str,
) -> str:
    s = TEXT[lang]
    na = "不适用" if lang == "zh" else "n/a"
    status_display = STATUS_ZH[status] if lang == "zh" else status
    report_id, evidence_id = report_identity(args, metrics)
    lines = [
        f"# {args.title}",
        "",
        f"**{s['report_id_label']}:** `{report_id}`  ",
        f"**{s['date']}:** {args.report_datetime}  ",
        f"**{s['evidence_label']}:** `{getattr(args, 'metrics', '')}`  ",
        f"**{s['tool_label']}:** [{repo_name_from_url(args.skill_url)}]({args.skill_url})",
        "",
        f"## {s['key_results']}",
        "",
    ]
    key_rows = key_result_rows(
        metrics,
        getattr(args, "primary", None),
        getattr(args, "baseline", None),
        lang,
    )
    if key_rows:
        method_ids = key_rows[0]["method_ids"]
        method_names = [labels.get(method_id, method_id) for method_id in method_ids]
        lines.append(
            "| "
            + " | ".join([s["key_dimension"], s["key_metric"], *method_names])
            + " |"
        )
        lines.append("|" + "---|" * (len(method_names) + 2))
        for row in key_rows:
            if row["delta"] is None:
                verdict = "—"
            elif abs(row["delta"]) < 1e-12:
                verdict = s["tie"]
            else:
                verdict = s["better"] if row["delta"] > 0 else s["worse"]
            cells = [row["dimension"], row["metric"]]
            for method_id in method_ids:
                value = row["values"].get(method_id, "—")
                if value != "—" and method_id in row["best_ids"]:
                    value = f"**{value}**"
                elif value != "—" and method_id in row["second_ids"]:
                    value = f"<u>{value}</u>"
                cells.append(value)
            lines.append("| " + " | ".join(cells) + " |")
    lines.extend(
        [
            "",
            f"## {s['protocol']}",
            "",
        ]
    )
    lines.extend(
        [
            "",
            f"| {s['setting']} | {s['value_label']} |",
            "|---|---|",
        ]
    )
    for label, value in configuration_rows(
        metrics, labels, lang, str(getattr(args, "metrics", "")), review_agg
    ):
        lines.append(f"| {label} | {value} |")
    lines.extend(
        [
            "",
            f"### {s['metrics_by_category']}",
            "",
            f"**{s['quantitative_metrics']}**",
            "",
            f"| {s['family_metric']} | {s['metric']} |",
            "|---|---|",
        ]
    )
    for family, names in metric_classification_rows(metrics, lang):
        lines.append(f"| {family} | {names} |")
    lines.extend(
        [
            "",
            f"**{s['qualitative_metrics']}**",
            "",
            f"| {s['dimension']} | {s['value_label']} |",
            "|---|---|",
        ]
    )
    for dimension in REVIEW_DIMENSIONS:
        lines.append(f"| {DIMENSION_LABELS[lang][dimension]} | 1-5 |")
    lines.append("")

    lines.extend(
        [
            f"### {s['data_config']}",
            "",
            f"| {s['setting']} | {s['value_label']} |",
            "|---|---|",
        ]
    )
    for label, value in data_profile_rows(metrics, lang):
        lines.append(f"| {label} | {value} |")
    lines.append("")

    lines.extend(["", f"## {s['quantitative']}", ""])
    for table in metric_tables(metrics, labels, lang):
        lines.append(f"### {table['heading']}")
        lines.append("")
        lines.append("| " + " | ".join(table["headers"]) + " |")
        lines.append("|" + "---|" * len(table["headers"]))
        for row in table["rows"]:
            cells = [f"{row['label']} {'↑' if row['higher_is_better'] else '↓'}"]
            for method_id in table["method_ids"]:
                value = stat_without_n(row["summaries"].get(method_id))
                if method_id in row["best_ids"] and value != "—":
                    value = f"**{value}**"
                elif method_id in row["second_ids"] and value != "—":
                    value = f"<u>{value}</u>"
                cells.append(value)
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        sample_note = table_sample_note(table)
        lines.append(
            f"{s['best_second_note']} "
            + (f"Valid clips: {sample_note}." if lang == "en" else f"有效片段数：{sample_note}。")
        )
        comment = family_comment(
            metrics, labels, getattr(args, "primary", None),
            getattr(args, "baseline", None), table, lang,
        )
        if comment:
            lines.append("")
            lines.append(f"*{s['comment_label']}:* {comment}")
        lines.append("")
    if paired_rows:
        lines.extend(
            [
                f"### {s['paired_effects']}",
                "",
                "| "
                + (s["method"] if lang == "zh" else "Metric")
                + " | Δ (positive favors primary) | dz | 95% CI | n |",
                "|---|---|---|---|---|",
            ]
        )
        for row in paired_rows:
            ci = (
                f"[{format_number(row['ci'][0])}, {format_number(row['ci'][1])}]"
                if row["ci"]
                else "—"
            )
            lines.append(
                f"| {row['label']} | {format_number(row['mean_difference_favors_primary'])} "
                f"| {format_number(row['effect_size_dz'])} | {ci} | {row['n']} |"
            )
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

    if analysis_sections:
        lines.extend(["", f"## {s['discussion']}", ""])
        for section in analysis_sections:
            lines.extend(
                [f"### {section['heading']}", "", section["text"], ""]
            )

    lines.extend(
        [
            "",
            f"## {s['conclusion']}",
            "",
            conclusion,
            "",
            *(
                [f"## {s['notes']}", "", *[f"- {note}" for note in report_notes(args, lang)], ""]
                if report_notes(args, lang)
                else []
            ),
            f"## {s['appendix']}",
            "",
            f"### {s['appendix_metric_definitions']}",
            "",
        ]
    )
    for definition in metric_definition_rows(metrics, lang):
        lines.extend(
            [
                f"#### {definition['name']}",
                "",
                f"**{s['availability']}:** {definition['available']}",
                "",
                f"$${definition['formula']}$$",
                "",
                f"**{s['motivation']}:** {definition['rationale']}",
                "",
                f"**{s['implementation']}:** {definition['caveat']}",
                "",
            ]
        )

    lines.extend(
        [
            f"### {s['appendix_dataset']}",
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

    lines.extend(["", f"### {s['appendix_per_case']}", ""])
    for case in metrics.get("cases", []):
        lines.append(f"#### {case.get('id')}")
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
            name = asset_name(case["contact_sheet"])
            lines.extend(
                [
                    "",
                    f"![{s['contact_sheet']} {case.get('id')}](assets/{name})",
                ]
            )
        lines.append("")

    lines.extend(
        [
            f"### {s['appendix_ablations']}",
            "",
            s["ablation_text"],
            "",
            f"### {s['appendix_failures']}",
            "",
            s["failure_text"],
            "",
            f"### {s['appendix_threats']}",
            "",
        ]
    )
    lines.extend(f"- {threat}" for threat in s["threats_list"])
    lines.extend(["", ""])
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
    analysis_sections: list[dict[str, str]],
    conclusion: str,
    paired_rows: list[dict[str, Any]],
    args: argparse.Namespace,
    lang: str,
) -> str:
    s = TEXT[lang]
    report_id, evidence_id = report_identity(args, metrics)
    na = "不适用" if lang == "zh" else "n/a"
    status_display = STATUS_ZH[status] if lang == "zh" else status
    table_html = []
    for table in metric_tables(metrics, labels, lang):
        header_cells = "".join(f"<th>{html.escape(cell)}</th>" for cell in table["headers"])
        body_rows = []
        for row in table["rows"]:
            cells = [
                f"{metric_button(row['metric'], row['label'], lang)} "
                f"{'↑' if row['higher_is_better'] else '↓'}"
            ]
            for method_id in table["method_ids"]:
                value = stat_without_n(row["summaries"].get(method_id))
                if method_id in row["best_ids"] and value != "—":
                    value = f"<strong>{html.escape(value)}</strong>"
                elif method_id in row["second_ids"] and value != "—":
                    value = f"<u>{html.escape(value)}</u>"
                else:
                    value = html.escape(value)
                cells.append(value)
            cell_html = "".join(f"<td>{cell}</td>" for cell in cells)
            body_rows.append(f"<tr>{cell_html}</tr>")
        sample_note = table_sample_note(table)
        comment = family_comment(
            metrics, labels, getattr(args, "primary", None),
            getattr(args, "baseline", None), table, lang,
        )
        if comment:
            comment = ("Comment: " if lang == "en" else "点评：") + comment
        table_html.append(
            f"<section><h3>{html.escape(table['heading'])}</h3>"
            f"<div class='table-wrap'><table><thead><tr>{header_cells}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody></table></div>"
            f"<p class='table-note'>{html.escape(s['best_second_note'])} "
            f"{html.escape('有效片段数' if lang == 'zh' else 'Valid clips')}: "
            f"{html.escape(sample_note)}.</p>"
            f"<p class='comment'>{html.escape(comment)}</p></section>"
        )

    paired_html = ""
    if paired_rows:
        paired_body = []
        for row in paired_rows:
            ci = (
                f"[{format_number(row['ci'][0])}, {format_number(row['ci'][1])}]"
                if row["ci"]
                else "—"
            )
            paired_body.append(
                "<tr>"
                f"<td>{html.escape(row['label'])}</td>"
                f"<td>{html.escape(format_number(row['mean_difference_favors_primary']))}</td>"
                f"<td>{html.escape(format_number(row['effect_size_dz']))}</td>"
                f"<td>{html.escape(ci)}</td>"
                f"<td>{row['n']}</td>"
                "</tr>"
            )
        paired_html = (
            f"<section><h3>{html.escape(s['paired_effects'])}</h3>"
            "<div class='table-wrap'><table><thead><tr>"
            f"<th>{html.escape('指标' if lang == 'zh' else 'Metric')}</th>"
            f"<th>{html.escape('Δ（正差值支持主方法）' if lang == 'zh' else 'Δ (positive favors primary)')}</th>"
            "<th>dz</th><th>95% CI</th><th>n</th></tr></thead><tbody>"
            + "".join(paired_body)
            + "</tbody></table></div></section>"
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
            name = asset_name(case["contact_sheet"])
            image = f"<img src='assets/{html.escape(name)}' alt='Contact sheet {html.escape(case.get('id', ''))}'>"
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
    analysis_html = ""
    if analysis_sections:
        analysis_html = (
            f"<section><h2>{html.escape(s['discussion'])}</h2>"
            + "".join(
                f"<div class='analysis-block'><h3>{html.escape(section['heading'])}</h3>"
                f"<p>{html.escape(section['text'])}</p></div>"
                for section in analysis_sections
            )
            + "</section>"
        )
    metric_defs_html = "".join(
        "<article class='metric-definition'>"
        f"<h3>{html.escape(definition['name'])}</h3>"
        f"<p class='availability'>{html.escape(definition['available'])}</p>"
        f"<div class='formula'>${definition['formula_tex']}$</div>"
        f"<p><b>{html.escape(s['motivation'])}:</b> {html.escape(definition['rationale'])}</p>"
        f"<p><b>{html.escape(s['implementation'])}:</b> {html.escape(definition['caveat'])}</p>"
        "</article>"
        for definition in metric_definition_rows(metrics, lang)
    )
    glance_rows = "".join(
        f"<tr><td>{html.escape(row['label'])}</td>"
        f"<td>{html.escape(row['dimension'])}</td>"
        f"<td>{html.escape(row['direction'])}</td>"
        f"<td>{html.escape(row['unit'])}</td></tr>"
        for row in metrics_at_a_glance_rows(metrics, lang)
    )
    glance_html = (
        f"<h3>{html.escape(s['metrics_glance'])}</h3>"
        "<div class='table-wrap'><table><thead><tr>"
        f"<th>{html.escape(s['metric'])}</th>"
        f"<th>{html.escape(s['dimension'])}</th>"
        f"<th>{html.escape(s['direction'])}</th>"
        f"<th>{html.escape(s['unit'])}</th>"
        f"</tr></thead><tbody>{glance_rows}</tbody></table></div>"
    )
    dataset_rows = []
    for case in metrics.get("cases", []):
        valid = [
            html.escape(labels.get(method_id, method_id))
            for method_id, result in case.get("methods", {}).items()
            if result.get("valid")
        ]
        warnings = html.escape("; ".join(case.get("warnings", [])) or s["none"])
        dataset_rows.append(
            "<tr>"
            f"<td>{html.escape(str(case.get('id')))}</td>"
            f"<td>{html.escape(str(case.get('content_id') or na))}</td>"
            f"<td>{html.escape(str(case.get('style_id') or na))}</td>"
            f"<td>{html.escape(str(case.get('split')))}</td>"
            f"<td>{', '.join(valid)}</td>"
            f"<td>{warnings}</td>"
            "</tr>"
        )
    dataset_html = (
        f"<h3>{html.escape(s['appendix_dataset'])}</h3>"
        "<div class='table-wrap'><table><thead><tr>"
        f"<th>{html.escape(s['case'])}</th><th>{html.escape(s['content'])}</th>"
        f"<th>{html.escape(s['style'])}</th><th>{html.escape(s['split'])}</th>"
        f"<th>{html.escape(s['valid_methods'])}</th><th>{html.escape(s['warnings'])}</th>"
        f"</tr></thead><tbody>{''.join(dataset_rows)}</tbody></table></div>"
    )

    experiment_data = metrics.get("experiment", {})
    protocol_rows_html = "".join(
        f"<tr><td>{html.escape(label)}</td><td>{html.escape(str(value))}</td></tr>"
        for label, value in configuration_rows(
            metrics, labels, lang, str(getattr(args, "metrics", "")), review_agg
        )
    )
    quant_rows_html = "".join(
        "<tr><td>"
        + html.escape(family)
        + "</td><td>"
        + ", ".join(
            metric_button(row["id"], row["label"], lang) for row in family_rows
        )
        + "</td></tr>"
        for family, family_rows in glance_by_family(metrics, lang)
    )
    qual_rows_html = "".join(
        "<tr><td>"
        + metric_button(
            dimension, DIMENSION_LABELS[lang][dimension], lang
        )
        + "</td><td>1-5</td></tr>"
        for dimension in REVIEW_DIMENSIONS
    )
    metric_config_html = (
        f"<section><h2>{html.escape(s['metrics_by_category'])}</h2>"
        f"<h3>{html.escape(s['quantitative_metrics'])}</h3>"
        "<div class='table-wrap'><table><thead><tr>"
        f"<th>{html.escape(s['family_metric'])}</th><th>{html.escape(s['metric'])}</th>"
        "</tr></thead><tbody>"
        + quant_rows_html
        + "</tbody></table></div>"
        f"<h3>{html.escape(s['qualitative_metrics'])}</h3>"
        "<div class='table-wrap'><table><thead><tr>"
        f"<th>{html.escape(s['dimension'])}</th><th>{html.escape(s['value_label'])}</th>"
        "</tr></thead><tbody>"
        + qual_rows_html
        + "</tbody></table></div></section>"
    )
    data_rows_html = "".join(
        f"<tr><td>{html.escape(label)}</td><td>{html.escape(str(value))}</td></tr>"
        for label, value in data_profile_rows(metrics, lang)
    )
    notes_html = ""
    if report_notes(args, lang):
        notes_html = (
            f"<section><h2>{html.escape(s['notes'])}</h2><ul>"
            + "".join(f"<li>{html.escape(note)}</li>" for note in report_notes(args, lang))
            + "</ul></section>"
        )
    data_config_html = (
        f"<section><h2>{html.escape(s['data_config'])}</h2>"
        "<div class='table-wrap'><table><thead><tr>"
        f"<th>{html.escape(s['setting'])}</th><th>{html.escape(s['value_label'])}</th>"
        f"</tr></thead><tbody>{data_rows_html}</tbody></table></div></section>"
    )
    key_rows = key_result_rows(
        metrics,
        getattr(args, "primary", None),
        getattr(args, "baseline", None),
        lang,
    )
    if key_rows:
        method_ids = key_rows[0]["method_ids"]
        method_names = [labels.get(mid, mid) for mid in method_ids]
        header_cells = "".join(
            f"<th>{html.escape(name)}</th>"
            for name in ([s["key_dimension"], s["key_metric"], *method_names])
        )
        body_rows = []
        for row in key_rows:
            cells = [
                f"<td class='dim'>{html.escape(row['dimension'])}</td>",
                f"<td class='metric'>"
                f"{metric_button(row['metric_id'], row['metric'], lang)}</td>",
            ]
            for method_id in method_ids:
                value = row["values"].get(method_id, "—")
                cell_class = ""
                if value != "—" and method_id in row["best_ids"]:
                    cell_class = "best"
                elif value != "—" and method_id in row["second_ids"]:
                    cell_class = "second"
                cells.append(f"<td class='{cell_class}'>{html.escape(value)}</td>")

            body_rows.append("<tr>" + "".join(cells) + "</tr>")
        key_table_html = (
            f"<section class='key-results'><h2>{html.escape(s['key_results'])}</h2>"
            "<div class='table-wrap'><table class='key-table'><thead><tr>"
            f"{header_cells}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div></section>"
        )
    else:
        key_table_html = ""

    coverage_body = "".join(
        "<tr>"
        f"<td>{html.escape(row['label'])}</td>"
        f"<td><span class='status {row['status']}'>"
        f"{html.escape(s['status_' + row['status']])}</span></td>"
        f"<td>{html.escape(row['evidence'])}</td>"
        "</tr>"
        for row in coverage_rows(metrics, lang)
    )
    family_text = " · ".join(
        f"{METRIC_DIMENSION_LABELS[lang].get(dimension, dimension)}: {count}"
        for dimension, count in metric_family_counts(metrics)
    )
    coverage_html = (
        f"<h3>{html.escape(s['coverage'])}</h3>"
        f"<p class='small'>{html.escape(s['coverage_note'])}</p>"
        "<div class='table-wrap'><table><thead><tr>"
        f"<th>{html.escape(s['parity_metric'])}</th>"
        f"<th>{html.escape(s['parity_status'])}</th>"
        f"<th>{html.escape(s['parity_evidence'])}</th>"
        f"</tr></thead><tbody>{coverage_body}</tbody></table></div>"
        f"<p class='small'>{html.escape(s['family_metric'])} — {html.escape(family_text)}</p>"
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
main {{ max-width:1120px; margin:0 auto; padding:32px 30px 60px; }}
header {{ background:linear-gradient(125deg,#102a2f,#1d5c63 60%,#2d7c76); color:white; padding:52px; border-radius:22px; }}
header h1 {{ margin:0 0 14px; font-size:42px; line-height:1.08; letter-spacing:-1.2px; }}
header p {{ max-width:760px; margin:8px 0; color:#dce9e8; }}
.badge {{ display:inline-block; margin-top:18px; padding:7px 12px; border:1px solid #a9cbca; border-radius:999px; font-weight:700; letter-spacing:.4px; }}
section, .case-card {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:20px 24px; margin-top:16px; box-shadow:0 8px 26px rgba(24,43,55,.04); }}
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
.table-note {{ color:var(--muted); font-size:12px; margin:10px 0 0; }}
.analysis-block {{ border-top:1px solid var(--line); padding-top:12px; margin-top:14px; }}
.analysis-block:first-of-type {{ border-top:0; padding-top:0; }} .analysis-block p {{ margin:0; }}
.kpi-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:14px; }}
.kpi {{ display:flex; flex-direction:column; gap:4px; border:1px solid var(--line); border-radius:14px; padding:16px 18px; background:linear-gradient(180deg,#fff,#f7fafb); }}
.kpi-dim {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }}
.kpi strong {{ font-size:24px; letter-spacing:-.5px; }}
.kpi-metric {{ font-size:12px; color:var(--muted); }}
.kpi-method {{ font-size:11px; color:var(--ink); }}
.kpi-delta {{ font-size:12px; font-weight:700; color:var(--muted); }}
.kpi-delta.up {{ color:#1d7a5f; }} .kpi-delta.down {{ color:#b5482c; }}
.kpi-bar {{ height:6px; border-radius:999px; background:#e8edf0; overflow:hidden; margin-top:6px; }}
.kpi-bar i {{ display:block; height:100%; background:linear-gradient(90deg,#2f8f78,#6db59b); }}
.status {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; }}
.status.present {{ background:#e6f4ee; color:#1d7a5f; }}
.status.proxy {{ background:#fdf1e2; color:#a7681f; }}
.status.missing {{ background:#fbeaea; color:#a33a2a; }}
.key-table th, .key-table td {{ padding:12px 14px; }}
.key-table td.dim {{ font-weight:700; color:var(--accent); white-space:nowrap; }}
.key-table td.metric {{ font-weight:700; }}
.key-table td.best {{ background:#e6f4ee; font-weight:800; }}
.key-table td.second {{ background:#f3f8f7; font-weight:600; text-decoration:underline 2px; text-underline-offset:3px; }}
.metric-link {{ background:none; border:0; padding:0; font:inherit; color:inherit; cursor:pointer; border-bottom:1px dotted var(--muted); }}
.metric-link:hover {{ color:var(--accent); }}
.metric-card {{ position:absolute; z-index:80; width:380px; max-width:calc(100vw - 24px); background:var(--panel);
  border:1px solid var(--line); border-radius:14px; box-shadow:0 18px 40px rgba(15,30,40,.22); padding:16px 18px;
  font-size:13px; color:var(--ink); display:none; }}
.metric-card h4 {{ margin:0 0 8px; font-size:15px; color:var(--accent); }}
.metric-card .mm-formula {{ background:#f0f4f5; border-radius:8px; padding:8px 10px; margin:8px 0;
  font-family:"Cambria Math","Times New Roman",serif; font-size:12.5px; overflow-x:auto; }}
.metric-card p {{ margin:6px 0; }}
.repo-link {{ display:inline-flex; align-items:center; gap:6px; color:#fff; text-decoration:none; font-weight:700; }}
.repo-link:hover {{ text-decoration:underline; }}
.verdict {{ display:inline-block; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:800; }}
.verdict.up {{ background:#e6f4ee; color:#1d7a5f; }}
.verdict.down {{ background:#fbeaea; color:#a33a2a; }}
.verdict.tie {{ background:#eef1f4; color:#607083; }}
.metric-definition {{ border-top:1px solid var(--line); padding-top:16px; margin-top:16px; }}
.metric-definition:first-of-type {{ border-top:0; padding-top:0; }}
.availability {{ display:inline-block; color:var(--accent); background:#eef6f5; border-radius:999px; padding:2px 9px; font-size:12px; font-weight:700; }}
.formula {{ margin:10px 0; padding:20px 18px; border-radius:10px; background:#f0f4f5; text-align:center; font:15px/1.6 "Cambria Math","Times New Roman",serif; overflow-x:auto; }}
@media print {{ body {{ background:#fff; }} main {{ max-width:none; padding:0; }} header {{ padding:28px 30px; border-radius:0; }} section {{ box-shadow:none; }} .kpi, .review-card, .case-card, tr {{ break-inside:avoid; }} }}
@media (max-width:700px) {{ main {{ padding:20px 12px 50px; }} header {{ padding:30px 22px; }} header h1 {{ font-size:31px; }} section,.case-card {{ padding:20px; }} .bar-row {{ grid-template-columns:110px 1fr 36px; font-size:12px; }} }}
</style>
<script>
window.MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }}, svg: {{ fontCache: 'global' }} }};
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
</head>
<body><main>
<header>
<h1>{html.escape(args.title)}</h1>
<p><strong>{html.escape(s['report_id_label'])}:</strong> <code>{report_id}</code></p>
<p><strong>{html.escape(s['date'])}:</strong> {html.escape(args.report_datetime)}</p>
<p><strong>{html.escape(s['evidence_label'])}:</strong> <code>{html.escape(str(getattr(args, 'metrics', '')))}</code></p>
<p><strong>{html.escape(s['tool_label'])}:</strong> <a class="repo-link" href="{html.escape(args.skill_url)}"><svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>{html.escape(repo_name_from_url(args.skill_url))}</a></p>
</header>
{key_table_html}
<section><h2>{html.escape(s['protocol'])}</h2><div class="table-wrap"><table><thead><tr><th>{html.escape(s['setting'])}</th><th>{html.escape(s['value_label'])}</th></tr></thead><tbody>{protocol_rows_html}</tbody></table></div></section>
{metric_config_html}{data_config_html}
<section><h2>{html.escape(s['quantitative'])}</h2>{''.join(table_html)}{paired_html}<p class="small">{html.escape(s['metrics_note'])}</p></section>
<section><h2>{html.escape(s['blind_review'])}</h2><div class="grid">{''.join(review_cards)}</div></section>
{analysis_html}
<section><h2>{html.escape(s['conclusion'])}</h2><p>{html.escape(conclusion)}</p></section>
{notes_html}
<section class="appendix"><h2>{html.escape(s['appendix'])}</h2>
<h3>{html.escape(s['appendix_metric_definitions'])}</h3>{metric_defs_html}
{dataset_html}
<h3>{html.escape(s['appendix_per_case'])}</h3><p class="small">{html.escape(s['per_case_note'])}</p>{''.join(case_sections)}
<h3>{html.escape(s['appendix_ablations'])}</h3><p>{html.escape(s['ablation_text'])}</p>
<h3>{html.escape(s['appendix_failures'])}</h3><p>{html.escape(s['failure_text'])}</p>
<h3>{html.escape(s['appendix_threats'])}</h3><ul>{''.join(f'<li>{html.escape(item)}</li>' for item in s['threats_list'])}</ul>
</section>
<script>
(function () {{
  if (window.__vstMetricCardInit) {{ return; }}
  window.__vstMetricCardInit = true;
  var card = document.createElement('div');
  card.className = 'metric-card';
  document.body.appendChild(card);
  function hide() {{ card.style.display = 'none'; }}
  function line(label, value) {{
    var el = document.createElement('p');
    el.textContent = label + ': ' + value;
    return el;
  }}
  document.addEventListener('click', function (event) {{
    var link = event.target.closest ? event.target.closest('.metric-link') : null;
    if (!link) {{ hide(); return; }}
    card.textContent = '';
    var title = document.createElement('h4');
    title.textContent = link.getAttribute('data-name') || '';
    card.appendChild(title);
    var formula = document.createElement('div');
    formula.className = 'mm-formula';
    formula.textContent = '$' + (link.getAttribute('data-formula') || '') + '$';
    card.appendChild(formula);
    card.appendChild(line('Motivation', link.getAttribute('data-why') || ''));
    card.appendChild(line('Caveat', link.getAttribute('data-caveat') || ''));
    card.style.display = 'block';
    var rect = link.getBoundingClientRect();
    card.style.left = Math.max(12, Math.min(rect.left, window.innerWidth - 400)) + 'px';
    card.style.top = (rect.bottom + window.scrollY + 8) + 'px';
    if (window.MathJax && window.MathJax.typesetPromise) {{
      window.MathJax.typesetPromise([card]).catch(function () {{}});
    }} else {{
      setTimeout(function () {{
        if (window.MathJax && window.MathJax.typesetPromise) {{
          window.MathJax.typesetPromise([card]).catch(function () {{}});
        }}
      }}, 900);
    }}
    event.stopPropagation();
  }});
  document.addEventListener('keydown', function (event) {{
    if (event.key === 'Escape') {{ hide(); }}
  }});
}})();
</script>
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
        # macOS: PingFang and Hiragino use PostScript outlines that ReportLab
        # cannot embed, so prefer the TrueType-flavoured system fonts first.
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
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
            "WenQuanYi Zen Hei is a Linux choice with TrueType outlines."
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


def pdf_rich_text(value: Any, lang: str = "en") -> str:
    escaped = html.escape(pdf_safe_text(value, lang))
    return (
        escaped.replace("[[B]]", "<b>")
        .replace("[[/B]]", "</b>")
        .replace("[[U]]", "<u>")
        .replace("[[/U]]", "</u>")
        .replace("[[G]]", '<font color="#1D7A5F">')
        .replace("[[/G]]", "</font>")
        .replace("[[R]]", '<font color="#B5482C">')
        .replace("[[/R]]", "</font>")
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
        Paragraph(pdf_rich_text(cell, lang), header_style)
        for cell in headers
    ]
    wrapped_rows = [
        [
            Paragraph(pdf_rich_text(cell, lang), body_style)
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
    analysis_sections: list[dict[str, str]],
    conclusion: str,
    paired_rows: list[dict[str, Any]],
    args: argparse.Namespace,
    lang: str,
    font_regular: str,
    font_bold: str,
) -> None:
    s = TEXT[lang]
    report_id, evidence_id = report_identity(args, metrics)
    na = "不适用" if lang == "zh" else "n/a"
    status_display = STATUS_ZH[status] if lang == "zh" else status
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=13 * mm,
        leftMargin=13 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=args.title,
        author="video-style-transfer-eval",
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "CoverTitle",
            parent=styles["Title"],
            fontName=font_bold,
            fontSize=24,
            leading=28,
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
            spaceBefore=8,
            spaceAfter=5,
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
            fontSize=8.0,
            leading=10.6,
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
            "Formula",
            parent=styles["BodyText"],
            fontName=font_regular,
            fontSize=8.1,
            leading=11.5,
            leftIndent=5,
            rightIndent=5,
            borderWidth=0,
            backColor=colors.HexColor("#F0F4F5"),
            borderPadding=7,
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
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(html.escape(args.title), styles["CoverTitle"]))
    story.append(
        Paragraph(
            f"<b>{html.escape(s['report_id_label'])}:</b> {html.escape(report_id)}<br/>"
            f"<b>{html.escape(s['date'])}:</b> {html.escape(args.report_datetime)}<br/>"
            f"<b>{html.escape(s['evidence_label'])}:</b> "
            f"{html.escape(str(getattr(args, 'metrics', '')))}<br/>"
            f"<b>{html.escape(s['tool_label'])}:</b> "
            f"<link href=\"{html.escape(args.skill_url)}\">"
            f"{html.escape(repo_name_from_url(args.skill_url))}</link>",
            styles["BodySmall"],
        )
    )
    story.append(Spacer(1, 6 * mm))

    key_rows = key_result_rows(
        metrics, args.primary, args.baseline, lang
    )
    if key_rows:
        story.append(
            Paragraph(html.escape(s["key_results"]), styles["Subsection"])
        )
        method_ids = key_rows[0]["method_ids"]
        method_names = [labels.get(method_id, method_id) for method_id in method_ids]
        key_table_rows = []
        for row in key_rows:
            cells = [row["dimension"], row["metric"]]
            for method_id in method_ids:
                value = row["values"].get(method_id, "—")
                if value != "—" and method_id in row["best_ids"]:
                    value = f"[[B]]{value}[[/B]]"
                elif value != "—" and method_id in row["second_ids"]:
                    value = f"[[U]]{value}[[/U]]"
                cells.append(value)
            key_table_rows.append(cells)
        story.append(
            pdf_table(
                [
                    s["key_dimension"],
                    s["key_metric"],
                    *method_names,
                ],
                key_table_rows,
                178 * mm,
                font_regular=font_regular,
                font_bold=font_bold,
                lang=lang,
            )
        )

    story.append(Paragraph(html.escape(s["protocol"]), styles["Subsection"]))
    experiment = metrics.get("experiment", {})
    story.append(
        pdf_table(
            [s["setting"], s["value_label"]],
            [
                [label, str(value)]
                for label, value in configuration_rows(
                    metrics, labels, lang, str(getattr(args, "metrics", "")), review_agg
                )
            ],
            178 * mm,
            font_regular=font_regular,
            font_bold=font_bold,
            lang=lang,
        )
    )

    story.append(Paragraph(html.escape(s["metrics_by_category"]), styles["Subsection"]))
    story.append(Paragraph(html.escape(s["quantitative_metrics"]), styles["BodySmall"]))
    story.append(
        pdf_table(
            [s["family_metric"], s["metric"]],
            [
                [family, names]
                for family, names in metric_classification_rows(metrics, lang)
            ],
            178 * mm,
            font_regular=font_regular,
            font_bold=font_bold,
            lang=lang,
        )
    )
    story.append(Paragraph(html.escape(s["qualitative_metrics"]), styles["BodySmall"]))
    story.append(
        pdf_table(
            [s["dimension"], s["value_label"]],
            [
                [DIMENSION_LABELS[lang][dimension], "1-5"]
                for dimension in REVIEW_DIMENSIONS
            ],
            178 * mm,
            font_regular=font_regular,
            font_bold=font_bold,
            lang=lang,
        )
    )
    story.append(Paragraph(html.escape(s["data_config"]), styles["Subsection"]))
    story.append(
        pdf_table(
            [s["setting"], s["value_label"]],
            [[label, value] for label, value in data_profile_rows(metrics, lang)],
            178 * mm,
            font_regular=font_regular,
            font_bold=font_bold,
            lang=lang,
        )
    )

    story.append(Paragraph(html.escape(s["quantitative"]), styles["Section"]))
    for table_data in metric_tables(metrics, labels, lang):
        story.append(Paragraph(html.escape(table_data["heading"]), styles["Subsection"]))
        rows = []
        for row in table_data["rows"]:
            values = [f"{row['label']} {'↑' if row['higher_is_better'] else '↓'}"]
            for method_id in table_data["method_ids"]:
                value = stat_without_n(row["summaries"].get(method_id))
                if method_id in row["best_ids"] and value != "—":
                    value = f"[[B]]{value}[[/B]]"
                elif method_id in row["second_ids"] and value != "—":
                    value = f"[[U]]{value}[[/U]]"
                values.append(value)
            rows.append(values)
        story.append(
            pdf_table(
                table_data["headers"],
                rows,
                178 * mm,
                font_regular=font_regular,
                font_bold=font_bold,
                lang=lang,
            )
        )
        story.append(
            Paragraph(
                html.escape(
                    s["best_second_note"]
                    + " "
                    + ("有效片段数" if lang == "zh" else "Valid clips")
                    + ": "
                    + table_sample_note(table_data)
                    + "."
                ),
                styles["BodySmall"],
            )
        )
        comment = family_comment(
            metrics, labels, args.primary, args.baseline, table_data, lang
        )
        if comment:
            story.append(
                Paragraph(
                    html.escape(
                        ("Comment: " if lang == "en" else "点评：") + comment
                    ),
                    styles["BodySmall"],
                )
            )
        story.append(Spacer(1, 4 * mm))

    if paired_rows:
        story.append(Paragraph(html.escape(s["paired_effects"]), styles["Subsection"]))
        paired_data = []
        for row in paired_rows:
            ci = (
                f"[{format_number(row['ci'][0])}, {format_number(row['ci'][1])}]"
                if row["ci"]
                else "—"
            )
            paired_data.append(
                [
                    row["label"],
                    format_number(row["mean_difference_favors_primary"]),
                    format_number(row["effect_size_dz"]),
                    ci,
                    str(row["n"]),
                ]
            )
        story.append(
            pdf_table(
                [
                    "Metric" if lang == "en" else "指标",
                    "Δ (positive favors primary)"
                    if lang == "en"
                    else "Δ（正差值支持主方法）",
                    "dz",
                    "95% CI",
                    "n",
                ],
                paired_data,
                178 * mm,
                font_regular=font_regular,
                font_bold=font_bold,
                lang=lang,
            )
        )

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

    if analysis_sections:
        story.append(Paragraph(html.escape(s["discussion"]), styles["Section"]))
        for section in analysis_sections:
            story.append(
                Paragraph(html.escape(section["heading"]), styles["Subsection"])
            )
            story.append(
                Paragraph(html.escape(section["text"]), styles["BodyCJK"])
            )

    story.append(PageBreak())
    story.append(Paragraph(html.escape(s["conclusion"]), styles["Section"]))
    story.append(Paragraph(html.escape(conclusion), styles["BodyCJK"]))
    if report_notes(args, lang):
        notes_block = [Paragraph(html.escape(s["notes"]), styles["Section"])]
        for note in report_notes(args, lang):
            notes_block.append(
                Paragraph(f"- {html.escape(note)}", styles["BodySmall"])
            )
        story.append(KeepTogether(notes_block))

    story.append(PageBreak())
    story.append(Paragraph(html.escape(s["appendix"]), styles["Section"]))
    story.append(
        Paragraph(
            html.escape(s["appendix_metric_definitions"]), styles["Subsection"]
        )
    )
    for definition in metric_definition_rows(metrics, lang):
        story.append(
            Paragraph(html.escape(definition["name"]), styles["Subsection"])
        )
        story.append(
            Paragraph(
                f"<b>{html.escape(s['availability'])}:</b> "
                f"{html.escape(definition['available'])}",
                styles["BodySmall"],
            )
        )
        story.append(
            Paragraph(html.escape(definition["formula"]), styles["Formula"])
        )
        story.append(
            Paragraph(
                f"<b>{html.escape(s['motivation'])}:</b> "
                f"{html.escape(definition['rationale'])}",
                styles["BodyCJK"],
            )
        )
        story.append(
            Paragraph(
                f"<b>{html.escape(s['implementation'])}:</b> "
                f"{html.escape(definition['caveat'])}",
                styles["BodySmall"],
            )
        )

    story.append(
        Paragraph(html.escape(s["appendix_dataset"]), styles["Subsection"])
    )
    dataset_rows = []
    for case in metrics.get("cases", []):
        valid = [
            labels.get(method_id, method_id)
            for method_id, result in case.get("methods", {}).items()
            if result.get("valid")
        ]
        dataset_rows.append(
            [
                str(case.get("id")),
                str(case.get("content_id") or na),
                str(case.get("style_id") or na),
                str(case.get("split")),
                ", ".join(valid),
                "; ".join(case.get("warnings", [])) or s["none"],
            ]
        )
    story.append(
        pdf_table(
            [
                s["case"],
                s["content"],
                s["style"],
                s["split"],
                s["valid_methods"],
                s["warnings"],
            ],
            dataset_rows,
            178 * mm,
            font_regular=font_regular,
            font_bold=font_bold,
            lang=lang,
        )
    )

    story.append(
        Paragraph(html.escape(s["appendix_per_case"]), styles["Subsection"])
    )
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
            asset_path = output_path.parent / "assets" / asset_name(case["contact_sheet"])
            image = fit_rl_image(asset_path, 174 * mm, 92 * mm)
            if image:
                story.append(Spacer(1, 3 * mm))
                story.append(image)
        story.append(Spacer(1, 5 * mm))

    story.append(
        Paragraph(html.escape(s["appendix_ablations"]), styles["Subsection"])
    )
    story.append(Paragraph(html.escape(s["ablation_text"]), styles["BodyCJK"]))
    story.append(
        Paragraph(html.escape(s["appendix_failures"]), styles["Subsection"])
    )
    story.append(Paragraph(html.escape(s["failure_text"]), styles["BodyCJK"]))
    threats_block = [
        Paragraph(html.escape(s["appendix_threats"]), styles["Subsection"])
    ]
    for threat in s["threats_list"]:
        threats_block.append(
            Paragraph(f"- {html.escape(threat)}", styles["BodySmall"])
        )
    story.append(KeepTogether(threats_block))

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


def latex_escape(value: Any) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "—": "--",
        "–": "--",
    }
    text = str(value)
    return "".join(replacements.get(character, character) for character in text)


def latex_stat(summary: dict[str, Any] | None) -> str:
    if not summary:
        return "--"
    return (
        f"${format_number(summary.get('mean'))} \\pm "
        f"{format_number(summary.get('std'))}$"
    )


def latex_ranked_stat(row: dict[str, Any], method_id: str) -> str:
    value = latex_stat(row["summaries"].get(method_id))
    if method_id in row["best_ids"] and value != "--":
        return rf"\textbf{{{value}}}"
    if method_id in row["second_ids"] and value != "--":
        return rf"\underline{{{value}}}"
    return value


def latex_report(
    metrics: dict[str, Any],
    labels: dict[str, str],
    review_agg: dict[str, Any],
    status: str,
    findings: list[str],
    recommendation: str,
    analysis_sections: list[dict[str, str]],
    conclusion: str,
    paired_rows: list[dict[str, Any]],
    args: argparse.Namespace,
    lang: str,
) -> str:
    s = TEXT[lang]
    report_id, evidence_id = report_identity(args, metrics)
    status_display = STATUS_ZH[status] if lang == "zh" else status
    if lang == "zh":
        document_class = r"\documentclass[UTF8,10pt]{ctexart}"
        default_font = r"\usepackage{lmodern}"
        labels_text = {
            "abstract": "摘要",
            "setup": "评估配置",
            "metric_definitions": "指标定义与设计动机",
            "motivation": "设计动机",
            "implementation": "解释与报告注意事项",
            "dataset": "数据与配对设计",
            "results": "实验结果",
            "review": "定性结果（VLM）",
            "analysis": "分析与讨论",
            "limitations": "局限性与有效性威胁",
            "conclusion": "结论",
            "recommendation": "建议",
            "appendix": "附录：单案例证据",
            "generated": "本报告由 video-style-transfer-eval 自动生成。",
            "metric": "评价指标",
            "direction": "方向",
            "method": "方法",
            "automated_report": "自动生成评估报告",
        }
    else:
        document_class = r"\documentclass[10pt]{article}"
        default_font = r"\usepackage{lmodern}"
        labels_text = {
            "abstract": "Abstract",
            "setup": "Evaluation Configuration",
            "metric_definitions": "Metric Definitions and Motivation",
            "motivation": "Motivation",
            "implementation": "Interpretation and reporting caveat",
            "dataset": "Data and Paired Design",
            "results": "Experimental Results",
            "review": "Qualitative Results (VLM)",
            "analysis": "Analysis and Discussion",
            "limitations": "Limitations and Threats to Validity",
            "conclusion": "Conclusion",
            "recommendation": "Recommendation",
            "appendix": "Appendix: Per-Case Evidence",
            "generated": "Generated by video-style-transfer-eval.",
            "metric": "Metric",
            "direction": "Direction",
            "method": "Method",
            "automated_report": "Automated Evaluation Report",
        }

    lines = [
        "% !TEX program = xelatex",
        document_class,
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{booktabs}",
        r"\usepackage{tabularx}",
        r"\usepackage{graphicx}",
        r"\usepackage{float}",
        r"\usepackage{caption}",
        r"\usepackage{hyperref}",
        r"\usepackage{xcolor}",
        default_font,
        r"\captionsetup{font=small,labelfont=bf}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{0.5em}",
        r"\newcommand{\best}[1]{\textbf{#1}}",
        r"\newcommand{\second}[1]{\underline{#1}}",
        r"\begin{document}",
        rf"\title{{{latex_escape(args.title)}}}",
        rf"\author{{{latex_escape(labels_text['automated_report'])}}}",
        rf"\date{{{latex_escape(s['report_id_label'])}: \texttt{{{latex_escape(report_id)}}} \\ {latex_escape(args.report_datetime)} \\ {latex_escape(s['tool_label'])}: \href{{{latex_escape(args.skill_url)}}}{{{latex_escape(repo_name_from_url(args.skill_url))}}}}}",
        r"\maketitle",
        r"\begin{abstract}",
        latex_escape(conclusion),
        r"\end{abstract}",
        rf"\section*{{{latex_escape(labels_text['setup'])}}}",
        r"\begin{tabular}{@{}ll@{}}",
        r"\toprule",
        rf"{latex_escape(s['setting'])} & {latex_escape(s['value_label'])} \\",
        r"\midrule",
    ]
    experiment = metrics.get("experiment", {})
    lines.extend(
        rf"{latex_escape(label)} & {latex_escape(str(value))} \\"
        for label, value in configuration_rows(
            metrics, labels, lang, str(getattr(args, "metrics", "--")), review_agg
        )
    )
    lines += [r"\bottomrule", r"\end{tabular}"]
    lines.append(rf"\subsection*{{{latex_escape(s['metrics_by_category'])}}}")
    lines.append(rf"\noindent\textbf{{{latex_escape(s['quantitative_metrics'])}}}")
    lines += [
        r"\begin{tabular}{@{}ll@{}}",
        r"\toprule",
        rf"{latex_escape(s['family_metric'])} & {latex_escape(s['metric'])} \\",
        r"\midrule",
    ]
    lines.extend(
        rf"{latex_escape(family)} & {latex_escape(names)} \\"
        for family, names in metric_classification_rows(metrics, lang)
    )
    lines += [r"\bottomrule", r"\end{tabular}"]
    lines.append(rf"\noindent\textbf{{{latex_escape(s['qualitative_metrics'])}}}")
    lines += [
        r"\begin{tabular}{@{}ll@{}}",
        r"\toprule",
        rf"{latex_escape(s['dimension'])} & {latex_escape(s['value_label'])} \\",
        r"\midrule",
    ]
    lines.extend(
        rf"{latex_escape(DIMENSION_LABELS[lang][dimension])} & 1-5 \\"
        for dimension in REVIEW_DIMENSIONS
    )
    lines += [r"\bottomrule", r"\end{tabular}"]
    lines.append(rf"\subsection*{{{latex_escape(s['data_config'])}}}")
    lines += [
        r"\begin{tabular}{@{}ll@{}}",
        r"\toprule",
        rf"{latex_escape(s['setting'])} & {latex_escape(s['value_label'])} \\",
        r"\midrule",
    ]
    lines.extend(
        rf"{latex_escape(label)} & {latex_escape(str(value))} \\"
        for label, value in data_profile_rows(metrics, lang)
    )
    lines += [r"\bottomrule", r"\end{tabular}"]
    lines.append(rf"\subsection*{{{latex_escape(s['key_results'])}}}")
    latex_key_rows = key_result_rows(metrics, args.primary, args.baseline, lang)
    latex_method_ids = latex_key_rows[0]["method_ids"] if latex_key_rows else []
    latex_method_names = [labels.get(mid, mid) for mid in latex_method_ids]
    lines += [
        r"\begin{tabular}{@{}ll" + "l" * len(latex_method_ids) + r"@{}}",
        r"\toprule",
        " & ".join(
            [
                latex_escape(s["key_dimension"]),
                latex_escape(s["key_metric"]),
                *[latex_escape(name) for name in latex_method_names],
            ]
        )
        + r" \\",
        r"\midrule",
    ]
    for row in latex_key_rows:
        cells = [latex_escape(row["dimension"]), latex_escape(row["metric"])]
        for method_id in latex_method_ids:
            value = row["values"].get(method_id, "--")
            if value != "--" and method_id in row["best_ids"]:
                value = rf"\textbf{{{latex_escape(value)}}}"
            elif value != "--" and method_id in row["second_ids"]:
                value = rf"\underline{{{latex_escape(value)}}}"
            else:
                value = latex_escape(value)
            cells.append(value)
        lines.append(" & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]

    lines.append(rf"\section*{{{latex_escape(labels_text['results'])}}}")

    for table_index, table in enumerate(metric_tables(metrics, labels, lang), start=1):
        columns = "l" + "c" * len(table["method_ids"])
        if lang == "zh":
            caption = (
                f"{table['heading']}结果。表中为有效配对片段上的均值和样本标准差。"
                f"{s['best_second_note']}箭头表示指标偏好方向。"
                f"有效片段数：{table_sample_note(table)}。"
            )
        else:
            caption = (
                f"{table['heading']} comparison. Mean and sample standard deviation "
                f"across valid paired clips. {s['best_second_note']} "
                f"Arrows denote preferred direction. Valid clips: {table_sample_note(table)}."
            )
        lines += [
            r"\begin{table}[H]",
            r"\centering",
            rf"\caption{{{latex_escape(caption)}}}",
            rf"\label{{tab:metrics-{table_index}}}",
            r"\small",
            r"\resizebox{\linewidth}{!}{%",
            rf"\begin{{tabular}}{{@{{}}{columns}@{{}}}}",
            r"\toprule",
            " & ".join(latex_escape(header) for header in table["headers"]) + r" \\",
            r"\midrule",
        ]
        for row in table["rows"]:
            cells = [
                f"{latex_escape(row['label'])} {'$\\uparrow$' if row['higher_is_better'] else '$\\downarrow$'}"
            ]
            cells.extend(
                latex_ranked_stat(row, method_id)
                for method_id in table["method_ids"]
            )
            lines.append(" & ".join(cells) + r" \\")
        lines += [
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\end{table}",
        ]
        comment = family_comment(
            metrics, labels, args.primary, args.baseline, table, lang
        )
        if comment:
            lines.append(
                r"\noindent\textit{"
                + latex_escape(("Comment: " if lang == "en" else "点评：") + comment)
                + "}"
            )

    if paired_rows:
        lines += [
            r"\begin{table}[H]",
            r"\centering",
            r"\caption{"
            + latex_escape(
                f"{s['paired_effects']}。差值为方向校正后的结果，正值支持主方法。"
                "dz 为描述性配对标准化效应量；当 n 小于五时不报告置信区间。"
                if lang == "zh"
                else
                f"{s['paired_effects']}. Differences are direction-adjusted so positive "
                "values favor the primary method. dz is the descriptive paired "
                "standardized effect; confidence intervals are omitted when n is less than five."
            )
            + "}",
            r"\label{tab:paired-effects}",
            r"\small",
            r"\begin{tabular}{@{}lrrrr@{}}",
            r"\toprule",
            f"{latex_escape(labels_text['metric'])} & $\\Delta$ & $d_z$ & 95\\% CI & $n$ \\\\",
            r"\midrule",
        ]
        for row in paired_rows:
            ci = (
                f"[{format_number(row['ci'][0])}, {format_number(row['ci'][1])}]"
                if row["ci"]
                else "--"
            )
            lines.append(
                f"{latex_escape(row['label'])} & "
                f"{format_number(row['mean_difference_favors_primary'])} & "
                f"{format_number(row['effect_size_dz'])} & {latex_escape(ci)} & {row['n']} \\\\"
            )
        lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]

    lines.append(rf"\section*{{{latex_escape(labels_text['review'])}}}")
    if review_agg["scored_count"]:
        review_columns = "l" + "c" * len(REVIEW_DIMENSIONS)
        lines += [
            r"\begin{table}[H]",
            r"\centering",
            r"\caption{"
            + latex_escape(
                "盲评视觉评分（1--5），所有维度均为越高越好。"
                if lang == "zh"
                else "Blinded visual scores (1--5). Higher is better for all dimensions."
            )
            + "}",
            r"\label{tab:vlm}",
            r"\small",
            r"\resizebox{\linewidth}{!}{%",
            rf"\begin{{tabular}}{{@{{}}{review_columns}@{{}}}}",
            r"\toprule",
            labels_text["method"]
            + " & "
            + " & ".join(
                latex_escape(DIMENSION_LABELS[lang][dimension])
                for dimension in REVIEW_DIMENSIONS
            )
            + r" \\",
            r"\midrule",
        ]
        for method in metrics.get("methods", []):
            method_id = method["id"]
            cells = [latex_escape(labels.get(method_id, method_id))]
            for dimension in REVIEW_DIMENSIONS:
                value = review_agg["method_dimension"][method_id][dimension]["mean"]
                cells.append("--" if value is None else f"{value:.2f}")
            lines.append(" & ".join(cells) + r" \\")
        lines += [r"\bottomrule", r"\end{tabular}%", r"}", r"\end{table}"]
        if review_agg["failure_counts"]:
            lines.append(
                r"\noindent\textbf{"
                + latex_escape(s["failure_tags"])
                + ":} "
                + latex_escape(
                    ", ".join(
                        f"{FAILURE_LABELS[lang].get(tag, tag)} ({count})"
                        for tag, count in review_agg["failure_counts"].most_common()
                    )
                )
                + r"\par"
            )
    else:
        lines.append(latex_escape(s["no_review"]))

    lines.append(rf"\section*{{{latex_escape(labels_text['analysis'])}}}")
    for section in analysis_sections:
        lines.extend(
            [
                rf"\subsection*{{{latex_escape(section['heading'])}}}",
                latex_escape(section["text"]),
            ]
        )

    lines += [
        rf"\section*{{{latex_escape(labels_text['conclusion'])}}}",
        latex_escape(conclusion),
    ]
    if report_notes(args, lang):
        lines.append(rf"\section*{{{latex_escape(s['notes'])}}}")
        lines.append(r"\begin{itemize}")
        lines.extend(rf"\item {latex_escape(note)}" for note in report_notes(args, lang))
        lines.append(r"\end{itemize}")
    lines += [
        r"\clearpage",
        rf"\section*{{{latex_escape(s['appendix'])}}}",
        rf"\subsection*{{{latex_escape(s['appendix_metric_definitions'])}}}",
    ]
    for definition in metric_definition_rows(metrics, lang):
        lines += [
            rf"\subsubsection*{{{latex_escape(definition['name'])}}}",
            rf"\textit{{{latex_escape(definition['available'])}}}",
            r"\begin{equation*}",
            definition["formula_tex"],
            r"\end{equation*}",
            rf"\textbf{{{latex_escape(labels_text['motivation'])}.}} {latex_escape(definition['rationale'])}",
            rf"\textbf{{{latex_escape(labels_text['implementation'])}.}} {latex_escape(definition['caveat'])}",
        ]
    lines.append(rf"\subsection*{{{latex_escape(s['appendix_dataset'])}}}")
    lines += [
        r"\begin{table}[H]",
        r"\centering",
        r"\caption{"
        + latex_escape(
            "配对评估案例及有效方法子集。"
            if lang == "zh"
            else "Paired evaluation cases and valid method subset."
        )
        + "}",
        r"\label{tab:dataset}",
        r"\small",
        r"\begin{tabularx}{\linewidth}{@{}lXlX@{}}",
        r"\toprule",
        rf"{latex_escape(s['case'])} & {latex_escape(s['content'])} / {latex_escape(s['style'])} & {latex_escape(s['split'])} & {latex_escape(s['valid_methods'])} \\",
        r"\midrule",
    ]
    for case in metrics.get("cases", []):
        valid = [
            labels.get(method_id, method_id)
            for method_id, result in case.get("methods", {}).items()
            if result.get("valid")
        ]
        lines.append(
            f"{latex_escape(case.get('id'))} & "
            f"{latex_escape(case.get('content_id') or '--')} / {latex_escape(case.get('style_id') or '--')} & "
            f"{latex_escape(case.get('split'))} & {latex_escape(', '.join(valid))} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
    lines.append(rf"\subsection*{{{latex_escape(s['appendix_per_case'])}}}")
    for case in metrics.get("cases", []):
        lines += [
            rf"\subsection*{{{latex_escape(case.get('id'))}}}",
            r"\begin{table}[H]",
            r"\centering",
            rf"\caption{{"
            + latex_escape(
                f"{case.get('id')} 的代表性指标。"
                if lang == "zh"
                else f"Selected metrics for {case.get('id')}."
            )
            + "}",
            r"\small",
            r"\begin{tabular}{@{}lcccc@{}}",
            r"\toprule",
            " & ".join(latex_escape(header) for header in s["per_case_headers"]) + r" \\",
            r"\midrule",
        ]
        for method_id, result in case.get("methods", {}).items():
            values = result.get("metrics", {}) if result.get("valid") else {}
            cells = [
                latex_escape(labels.get(method_id, method_id)),
                format_number(values.get("ssim")),
                format_number(values.get("lab_palette_w1")),
                format_number(values.get("offset_1_warp_rmse")),
                format_number(values.get("offset_1_flow_epe")),
            ]
            lines.append(" & ".join(cells) + r" \\")
        lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
        if case.get("contact_sheet"):
            name = asset_name(case["contact_sheet"])
            lines += [
                r"\begin{figure}[H]",
                r"\centering",
                rf"\includegraphics[width=\linewidth]{{assets/{latex_escape(name)}}}",
                rf"\caption{{"
                + latex_escape(
                    f"{case.get('id')} 的盲评源视频、风格参考与候选结果比较。"
                    if lang == "zh"
                    else
                    f"Blinded source, style, and candidate comparison for {case.get('id')}."
                )
                + "}",
                r"\end{figure}",
            ]

    lines.append(rf"\subsection*{{{latex_escape(s['appendix_ablations'])}}}")
    lines.append(latex_escape(s["ablation_text"]))
    lines.append(rf"\subsection*{{{latex_escape(s['appendix_failures'])}}}")
    lines.append(latex_escape(s["failure_text"]))
    lines += [
        rf"\subsection*{{{latex_escape(s['appendix_threats'])}}}",
        r"\begin{itemize}",
    ]
    lines.extend(rf"\item {latex_escape(threat)}" for threat in s["threats_list"])
    lines.append(r"\end{itemize}")

    lines += [

        r"\end{document}",
        "",
    ]
    return "\n".join(lines)


def copy_contact_sheets(
    metrics: dict[str, Any],
    assets_dir: Path,
    metrics_dir: Path,
) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)
    for case in metrics.get("cases", []):
        source = case.get("contact_sheet")
        if not source:
            continue
        source_path = resolve_asset_source(source, metrics_dir)
        if source_path.is_file():
            shutil.copy2(source_path, assets_dir / asset_name(source))


def print_pdf_with_chrome(
    chrome_path: str,
    html_path: Path,
    pdf_path: Path,
) -> None:
    """Print the HTML report to PDF with headless Chrome."""
    command = [
        chrome_path,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        html_path.resolve().as_uri(),
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=180
    )
    if completed.returncode != 0 or not pdf_path.is_file():
        raise RuntimeError(
            "Chrome PDF printing failed:\n"
            f"{completed.stdout[-800:]}\n{completed.stderr[-800:]}"
        )


def main() -> None:
    args = parse_args()
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    review = load_review(args.review)
    status = args.status or infer_status(metrics, review)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    copy_contact_sheets(metrics, args.output_dir / "assets", args.metrics.parent)
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
        analysis_sections = make_analysis_sections(
            metrics,
            labels,
            review_agg,
            args.primary,
            args.baseline,
            lang,
        )
        conclusion = make_conclusion(
            metrics,
            labels,
            review_agg,
            args.primary,
            args.baseline,
            status,
            lang,
        )
        paired_rows = (
            paired_effect_rows(
                metrics,
                args.primary,
                args.baseline,
                labels,
                lang,
            )
            if args.primary and args.baseline
            else []
        )
        suffix = f"_{lang}" if args.language == "both" else ""
        markdown_path = args.output_dir / f"report{suffix}.md"
        html_path = args.output_dir / f"report{suffix}.html"
        pdf_path = args.output_dir / f"report{suffix}.pdf"
        latex_path = args.output_dir / f"report{suffix}.tex"
        markdown = markdown_report(
            metrics,
            labels,
            review_agg,
            status,
            findings,
            recommendation,
            analysis_sections,
            conclusion,
            paired_rows,
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
            analysis_sections,
            conclusion,
            paired_rows,
            render_args,
            lang,
        )
        html_path.write_text(html_content, encoding="utf-8")
        if args.pdf_engine == "chrome" and Path(args.chrome_path).is_file():
            print_pdf_with_chrome(args.chrome_path, html_path, pdf_path)
        else:
            pdf_report(
                pdf_path,
                metrics,
                labels,
                review_agg,
                status,
                findings,
                recommendation,
                analysis_sections,
                conclusion,
                paired_rows,
                render_args,
                lang,
                cjk_regular if lang == "zh" else "Helvetica",
                cjk_bold if lang == "zh" else "Helvetica-Bold",
            )
        latex_content = latex_report(
            metrics,
            labels,
            review_agg,
            status,
            findings,
            recommendation,
            analysis_sections,
            conclusion,
            paired_rows,
            render_args,
            lang,
        )
        latex_path.write_text(latex_content, encoding="utf-8")
        print(f"Wrote {markdown_path}")
        print(f"Wrote {html_path}")
        print(f"Wrote {pdf_path}")
        print(f"Wrote {latex_path}")


if __name__ == "__main__":
    main()
