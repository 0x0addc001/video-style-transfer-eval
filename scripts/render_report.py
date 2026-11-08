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
        "metric_definitions": "Metric definitions and motivation",
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
        "perceptual_analysis": "Perceptual review and failure modes",
        "cost_analysis": "Computational cost",
        "synthesis": "Synthesis",
        "paired_effects": "Paired comparison against the primary baseline",
        "best_second_note": "Best and second-best mean values are shown in bold and underlined, respectively.",
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
        "metric_definitions": "指标定义与设计动机",
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
        "perceptual_analysis": "感知审查与失败模式",
        "cost_analysis": "计算成本",
        "synthesis": "综合判断",
        "paired_effects": "相对主基线的配对比较",
        "best_second_note": "最优和次优均值分别以粗体和下划线标出。",
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
        "available_keys": ["offset_1_warp_rmse", "offset_5_warp_rmse"],
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
]


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
            rows.append(
                {
                    "metric": metric,
                    "label": metric_label(lang, metric, info),
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

    style_metrics = ["clip_i", "lab_palette_w1", "lab_ab_palette_w1"]
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

    content_metrics = ["lpips", "clip_f", "ssim", "psnr"]
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

    category_votes = [sum(style_votes), sum(content_votes), sum(temporal_votes), sum(cost_votes)]
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

    return [
        {"heading": s["style_analysis"], "text": style_text},
        {"heading": s["content_analysis"], "text": content_text},
        {"heading": s["temporal_analysis"], "text": temporal_text},
        {"heading": s["perceptual_analysis"], "text": perceptual_text},
        {"heading": s["cost_analysis"], "text": cost_text},
        {"heading": s["synthesis"], "text": synthesis_text},
    ]


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
                f"本报告用 {valid_cases} 个合成案例验证了评估流程，未提供真实模型性能证据。"
                "结果表、感知分析和结论仍保留多维证据，不应被解释为 EchoStyle 或本文方法的基准排名。"
            )
        suffix = (
            "由于独立片段数量少于五个，当前差异未配套稳定置信区间，应视为探索性比较。"
            if valid_cases < 5
            else "应结合配对差值的置信区间判断差异稳定性和实际意义。"
        )
        return (
            "评估显示风格、内容、运动和成本目标之间可能存在权衡；"
            "只有在替代方案取得相近风格强度后才可解释保持性差异。"
            + suffix
        )
    if status == "Exploratory":
        return (
            f"This report uses {valid_cases} synthetic cases to validate the evaluation "
            "pipeline and does not provide evidence of real model performance. The "
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
        "The evaluation indicates that style, content, motion, and cost objectives may "
        "trade off. Preservation differences are interpretable only after methods are "
        "compared at similar achieved style strength. "
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
        "offset_1_warp_rmse",
        "offset_1_flow_epe",
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
            f"## {s['metric_definitions']}",
            "",
        ]
    )
    for definition in metric_definition_rows(metrics, lang):
        lines.extend(
            [
                f"### {definition['name']}",
                "",
                f"**{'可用性' if lang == 'zh' else 'Availability'}:** {definition['available']}",
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
    lines.extend(
        [
            "",
            f"## {s['conclusion']}",
            "",
            conclusion,
            "",
            f"### {s['recommendation']}",
            "",
            recommendation,
            "",
        ]
    )
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
    na = "不适用" if lang == "zh" else "n/a"
    status_display = STATUS_ZH[status] if lang == "zh" else status
    table_html = []
    for table in metric_tables(metrics, labels, lang):
        header_cells = "".join(f"<th>{html.escape(cell)}</th>" for cell in table["headers"])
        body_rows = []
        for row in table["rows"]:
            cells = [
                f"{html.escape(row['label'])} {'↑' if row['higher_is_better'] else '↓'}"
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
        table_html.append(
            f"<section><h3>{html.escape(table['heading'])}</h3>"
            f"<div class='table-wrap'><table><thead><tr>{header_cells}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody></table></div>"
            f"<p class='table-note'>{html.escape(s['best_second_note'])} "
            f"{html.escape('有效片段数' if lang == 'zh' else 'Valid clips')}: "
            f"{html.escape(sample_note)}.</p></section>"
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
        f"<div class='formula'>{html.escape(definition['formula'])}</div>"
        f"<p><b>{html.escape(s['motivation'])}:</b> {html.escape(definition['rationale'])}</p>"
        f"<p><b>{html.escape(s['implementation'])}:</b> {html.escape(definition['caveat'])}</p>"
        "</article>"
        for definition in metric_definition_rows(metrics, lang)
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
.table-note {{ color:var(--muted); font-size:12px; margin:10px 0 0; }}
.analysis-block {{ border-top:1px solid var(--line); padding-top:12px; margin-top:14px; }}
.analysis-block:first-of-type {{ border-top:0; padding-top:0; }} .analysis-block p {{ margin:0; }}
.metric-definition {{ border-top:1px solid var(--line); padding-top:16px; margin-top:16px; }}
.metric-definition:first-of-type {{ border-top:0; padding-top:0; }}
.availability {{ display:inline-block; color:var(--accent); background:#eef6f5; border-radius:999px; padding:2px 9px; font-size:12px; font-weight:700; }}
.formula {{ margin:10px 0; padding:20px 18px; border-radius:10px; background:#f0f4f5; text-align:center; font:15px/1.6 "Cambria Math","Times New Roman",serif; overflow-x:auto; }}
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
<section><h2>{html.escape(s['metric_definitions'])}</h2>{metric_defs_html}</section>
<section><h2>{html.escape(s['quantitative'])}</h2>{''.join(table_html)}{paired_html}<p class="small">{html.escape(s['metrics_note'])}</p></section>
<section><h2>{html.escape(s['blind_review'])}</h2><div class="grid">{''.join(review_cards)}</div></section>
{analysis_html}
<section><h2>{html.escape(s['per_case'])}</h2><p class="small">{html.escape(s['per_case_note'])}</p>{''.join(case_sections)}</section>
<section><h2>{html.escape(s['threats'])}</h2><ul>{''.join(f'<li>{html.escape(item)}</li>' for item in s['threats_list'])}</ul></section>
<section class="recommendation"><h2>{html.escape(s['conclusion'])}</h2><p>{html.escape(conclusion)}</p><h3>{html.escape(s['recommendation'])}</h3><p>{html.escape(recommendation)}</p></section>
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

    story.append(Paragraph(html.escape(s["metric_definitions"]), styles["Section"]))
    for definition in metric_definition_rows(metrics, lang):
        story.append(
            Paragraph(html.escape(definition["name"]), styles["Subsection"])
        )
        story.append(
            Paragraph(
                f"<b>{html.escape('可用性' if lang == 'zh' else 'Availability')}:</b> "
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
    closing_block.append(Paragraph(html.escape(s["conclusion"]), styles["Section"]))
    closing_block.append(Paragraph(html.escape(conclusion), styles["BodyCJK"]))
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
    status_display = STATUS_ZH[status] if lang == "zh" else status
    if lang == "zh":
        document_class = r"\documentclass[UTF8,10pt]{ctexart}"
        default_font = r"\usepackage{lmodern}"
        labels_text = {
            "abstract": "摘要",
            "setup": "评估设置与可复现性",
            "metric_definitions": "指标定义与设计动机",
            "motivation": "设计动机",
            "implementation": "解释与报告注意事项",
            "dataset": "数据与配对设计",
            "results": "实验结果",
            "review": "盲评视觉分析",
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
            "setup": "Evaluation Setup and Reproducibility",
            "metric_definitions": "Metric Definitions and Motivation",
            "motivation": "Motivation",
            "implementation": "Interpretation and reporting caveat",
            "dataset": "Data and Paired Design",
            "results": "Experimental Results",
            "review": "Blinded Visual Analysis",
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
        rf"\date{{{latex_escape(args.report_date)} \quad \textbf{{{latex_escape(s['claim_status'])}: {latex_escape(status_display)}}}}}",
        r"\maketitle",
        r"\begin{abstract}",
        latex_escape(args.claim),
        r"\par",
        latex_escape(conclusion),
        r"\end{abstract}",
        rf"\section*{{{latex_escape(labels_text['setup'])}}}",
        rf"\textbf{{{latex_escape(s['evidence_gates'])}}}",
        r"\begin{center}",
        r"\small",
        r"\begin{tabular}{@{}lll@{}}",
        r"\toprule",
        rf"{latex_escape(s['gate'])} & {latex_escape(s['value'])} & {latex_escape(s['status'])} \\",
        r"\midrule",
    ]
    for item, value, gate in evidence_rows(metrics, review_agg, status, lang):
        lines.append(
            f"{latex_escape(item)} & {latex_escape(value)} & {latex_escape(gate)} \\\\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{center}",
        r"\begin{itemize}",
    ]
    experiment = metrics.get("experiment", {})
    lines.extend(
        [
            rf"\item {latex_escape(s['flow_implementation'])}: {latex_escape(experiment.get('flow_implementation', '--'))}",
            rf"\item {latex_escape(s['sample_frames'])}: {latex_escape(experiment.get('frame_limit', '--'))}",
            rf"\item {latex_escape(s['temporal_offsets'])}: {latex_escape(experiment.get('temporal_offsets', '--'))}",
            rf"\item {latex_escape(s['blinding'])}: {latex_escape(experiment.get('blind', False))}",
            r"\end{itemize}",
            rf"\section*{{{latex_escape(labels_text['metric_definitions'])}}}",
        ]
    )
    for definition in metric_definition_rows(metrics, lang):
        lines.extend(
            [
                rf"\subsection*{{{latex_escape(definition['name'])}}}",
                rf"\textit{{{latex_escape(definition['available'])}}}",
                r"\begin{equation*}",
                definition["formula_tex"],
                r"\end{equation*}",
                rf"\textbf{{{latex_escape(labels_text['motivation'])}.}} {latex_escape(definition['rationale'])}",
                rf"\textbf{{{latex_escape(labels_text['implementation'])}.}} {latex_escape(definition['caveat'])}",
            ]
        )
    lines += [
            rf"\section*{{{latex_escape(labels_text['dataset'])}}}",
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
    lines += [
        r"\bottomrule",
        r"\end{tabularx}",
        r"\end{table}",
        rf"\section*{{{latex_escape(labels_text['results'])}}}",
    ]

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
        rf"\section*{{{latex_escape(labels_text['limitations'])}}}",
        r"\begin{itemize}",
    ]
    lines.extend(rf"\item {latex_escape(threat)}" for threat in s["threats_list"])
    lines += [
        r"\end{itemize}",
        rf"\section*{{{latex_escape(labels_text['conclusion'])}}}",
        latex_escape(conclusion),
        rf"\subsection*{{{latex_escape(labels_text['recommendation'])}}}",
        latex_escape(recommendation),
        r"\clearpage",
        rf"\section*{{{latex_escape(labels_text['appendix'])}}}",
    ]
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
            asset_name = Path(case["contact_sheet"]).name
            lines += [
                r"\begin{figure}[H]",
                r"\centering",
                rf"\includegraphics[width=\linewidth]{{assets/{latex_escape(asset_name)}}}",
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

    lines += [
        rf"\textit{{{latex_escape(labels_text['generated'])}}}",
        r"\end{document}",
        "",
    ]
    return "\n".join(lines)


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
