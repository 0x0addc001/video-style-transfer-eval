#!/usr/bin/env python3
"""Generate Beamer slide decks from evaluation directories (LaTeX, XeTeX)."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

OUT = Path("evaluation_run")

PREAMBLE = r"""
\documentclass[aspectratio=169,11pt]{beamer}
\usepackage{xeCJK}
\setCJKmainfont{PingFang SC}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{colortbl}
\usepackage{graphicx}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usepackage{tabularx}
\usepackage{ragged2e}

\definecolor{navy}{RGB}{0,32,96}
\definecolor{blue}{RGB}{31,78,156}
\definecolor{lightblue}{RGB}{220,230,245}
\definecolor{ink}{RGB}{31,41,55}
\definecolor{muted}{RGB}{96,112,128}

\setbeamercolor{normal text}{fg=ink}
\setbeamercolor{frametitle}{fg=navy}
\setbeamercolor{structure}{fg=navy}
\setbeamercolor{footline}{fg=muted}
\setbeamertemplate{navigation symbols}{}
\setbeamertemplate{itemize item}{\color{navy}$\blacktriangleright$}
\setbeamerfont{frametitle}{size=\LARGE,series=\bfseries}
\setbeamerfont{title}{size=\Huge,series=\bfseries}
\setbeamertemplate{frametitle}{%
  \vspace{0.35em}\insertframetitle\par
  \vspace{0.15em}{\color{navy}\rule{\textwidth}{1.2pt}}%
}
\setbeamertemplate{footline}{%
  \hbox to \paperwidth{\hspace{0.6cm}%
    {\scriptsize\color{muted}__REPORT_ID__}\hfill
    {\scriptsize\color{muted}\insertframenumber\,/\,\inserttotalframenumber}%
    \hspace{0.6cm}}\vspace{0.25em}%
}
\setlength{\parindent}{0pt}
\renewcommand{\arraystretch}{1.25}
\newcommand{\headrow}[1]{\color{white}\bfseries #1}
"""

STYLE_ZH = {
    "ghibli": "吉卜力", "van_gogh": "梵高", "sketch": "素描", "watercolor": "水彩",
    "monet": "莫奈", "paper_cutting": "剪纸", "american_cartoon": "美式卡通",
    "irasutoya": "Irasutoya", "jojo": "JoJo", "ukiyo_e": "浮世绘",
    "simpsons": "辛普森", "3d_chibi": "3D Q 版",
}
STYLE_EN = {
    "ghibli": "Ghibli", "van_gogh": "Van Gogh", "sketch": "Sketch", "watercolor": "Watercolor",
    "monet": "Monet", "paper_cutting": "Paper cutting", "american_cartoon": "American cartoon",
    "irasutoya": "Irasutoya", "jojo": "JoJo", "ukiyo_e": "Ukiyo-e",
    "simpsons": "Simpsons", "3d_chibi": "3D chibi",
}
TAG_EN = {
    "flicker": "flicker", "texture_sticking": "texture sticking", "detail_loss": "detail loss",
    "geometry_melting": "geometry melting", "color_bleed": "colour bleed",
    "edge_ghosting": "edge ghosting", "temporal_jump": "temporal jump", "identity_drift": "identity drift",
}

FIXED_EN = {
    "报告 ID": "Report ID",
    "评估概览": "Evaluation overview",
    "关键结果": "Key results",
    "按风格结果（12 种）": "Results by style (12)",
    "按风格结果": "Results by style",
    "按风格对比": "Comparison by style",
    "各风格 SSIM": "SSIM by style",
    "关键对比": "Key comparison",
    "SSIM（越高越好）": "SSIM (higher is better)",
    "亮度闪烁（越低越好）": "Luminance flicker (lower is better)",
    "SSIM 差距": "SSIM gap",
    "闪烁差距": "Flicker gap",
    "（吉卜力更低）": "(Ghibli lower)",
    "定性评估（VLM）": "Qualitative assessment (VLM)",
    "VBench 七维": "VBench (7 dimensions)",
    "维度": "Dimension",
    "均分": "Mean",
    "说明": "Description",
    "方向": "Direction",
    "评审设置": "Review setup",
    "单盲 contact sheet，每条只给目标风格。": "single-blind contact sheets with the target style.",
    "失败标签": "Failure tags",
    "示例": "Example",
    "结论与限制": "Conclusion and limitations",
    "谢谢！": "Thank you!",
    "越高越好": "higher is better",
    "越接近 0.5 越好": "closer to 0.5 is better",
    "较深蓝底：SSIM 最优；较浅蓝底：SSIM 最差；SSIM 越高越好，闪烁与重映射越低越好。":
        "Higher SSIM is better; best/worst are marked in the table.",
    "项目": "Item",
    "内容": "Content",
    "指标": "Metric",
    "数值": "Value",
    "风格": "Style",
    "闪烁": "Flicker",
    "重映射": "Warp",
    "方法": "Method",
    "Contact sheet：源视频帧与盲化候选。": "Contact sheet: source frames and blinded candidates.",
    "Contact sheet：源视频帧 + 吉卜力风格候选。": "Contact sheet: source frames and Ghibli candidates.",
    "Contact sheet：舞蹈视频的吉卜力风格候选。": "Contact sheet: Ghibli candidates for the dance clip.",
    "VBench 0.1.5，custom\\_input 模式；分数已按 VBench 归一化。":
        "VBench 0.1.5, custom\\_input mode; scores are normalised by VBench.",
}

TAG_ZH = {
    "flicker": "闪烁", "texture_sticking": "纹理粘连", "detail_loss": "细节损失",
    "geometry_melting": "几何融化", "color_bleed": "颜色渗漏", "edge_ghosting": "边缘重影",
    "temporal_jump": "时序跳变", "identity_drift": "身份漂移",
}


def fill(template: str, **values: object) -> str:
    text = template
    for key, value in values.items():
        text = text.replace(f"__{key}__", str(value))
    return text


def fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def style_stats(metrics, method_id="echostyle"):
    per = {}
    for case in metrics["cases"]:
        record = case["methods"][method_id]
        if not record.get("valid"):
            continue
        key = case["style_id"].lower().replace(" ", "_").replace("-", "_")
        per.setdefault(key, []).append(record["metrics"])
    return {
        key: {
            "n": len(values),
            "ssim": statistics.mean(v["ssim"] for v in values),
            "psnr": statistics.mean(v["psnr"] for v in values),
            "flicker": statistics.mean(v["luminance_flicker"] for v in values),
            "warp": statistics.mean(v["offset_1_warp_rmse"] for v in values),
        }
        for key, values in per.items()
    }


def review_stats(review, metrics):
    dims = ["style_adherence", "content_preservation", "temporal_stability",
            "artifact_control", "overall_visual_quality"]
    scores, tags = [], {}
    for entry in review["reviews"]:
        for score in entry["scores"]:
            scores.append(score)
            for tag in score.get("failure_tags", []):
                tags[tag] = tags.get(tag, 0) + 1
    return {d: statistics.mean(s[d] for s in scores) for d in dims}, tags


def bullets(items) -> str:
    return "\n".join(f"\\item \\textbf{{{head}}} {body}" for head, body in items)


def build(spec: dict) -> Path:
    lang = spec.get("lang", "zh")
    directory = Path(spec["dir"])
    metrics = spec.get("metrics")
    if metrics is None:
        metrics = json.loads((directory / "run" / "metrics.json").read_text(encoding="utf-8"))
    review = spec.get("review")
    if review is None:
        review_path = directory / "run" / "review_packet" / "validated_reviews.json"
        if not review_path.is_file():
            review_path = directory / "review_packet" / "validated_reviews.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
    report_files = sorted((directory / "report").glob("report_zh_VST-*.pdf"))
    report_id = spec.get("report_id") or (
        report_files[-1].stem.split("_")[2] if report_files else "VST"
    )

    method_id = spec.get("method_id") or next(iter(metrics["aggregates"]))
    aggregate = metrics["aggregates"][method_id]
    styles = style_stats(metrics, method_id)
    order = [s for s in spec["style_order"] if s in styles]
    vlm, tags = review_stats(review, metrics)
    cost = spec.get("cost", {})
    csd = spec.get("csd", {})

    frames = []
    extra: dict[str, object] = {}
    missing_rows: list[tuple[str, str]] = []
    has_style_image = any(case.get("style_image") for case in metrics.get("cases", []))
    if lang == "zh":
        if not has_style_image:
            missing_rows.append(("LAB 调色板 W1 / 色度 W1", "无风格参考图（文本驱动方法）"))
        if cost.get("runtime_s") is None:
            missing_rows.append(("运行时长", "未记录逐条推理耗时"))
        if cost.get("peak_memory_gb") is None:
            missing_rows.append(("峰值显存", "未采样峰值显存"))
        if not csd:
            missing_rows.append(("CSD-S / CSD-C", "未运行 CSD 外部评测器"))
        if not spec.get("vbench"):
            missing_rows.append(("VBench 七维", "未运行 VBench"))
    else:
        if not has_style_image:
            missing_rows.append(("LAB palette W1 / chroma W1", "no style reference image (text-driven method)"))
        if cost.get("runtime_s") is None:
            missing_rows.append(("Runtime", "per-clip runtime not recorded"))
        if cost.get("peak_memory_gb") is None:
            missing_rows.append(("Peak GPU memory", "peak memory not sampled"))
        if not csd:
            missing_rows.append(("CSD-S / CSD-C", "CSD evaluator not run"))
        if not spec.get("vbench"):
            missing_rows.append(("VBench dimensions", "VBench not run"))
    if missing_rows:
        if lang == "zh":
            body_rows = "\n".join(f"{name} & {reason} \\\\" for name, reason in missing_rows)
            frames.append(r"""
\begin{frame}{缺失指标及原因}
\small
\begin{tabular}{p{5.2cm}p{8.2cm}}
\toprule
\rowcolor{navy}\headrow{指标} & \headrow{原因} \\
\midrule
__MISSING_ROWS__
\bottomrule
\end{tabular}
\end{frame}
""")
        else:
            body_rows = "\n".join(f"{name} & {reason} \\\\" for name, reason in missing_rows)
            frames.append(r"""
\begin{frame}{Missing metrics and reasons}
\small
\begin{tabular}{p{5.6cm}p{7.8cm}}
\toprule
\rowcolor{navy}\headrow{Metric} & \headrow{Reason} \\
\midrule
__MISSING_ROWS__
\bottomrule
\end{tabular}
\end{frame}
""")
        extra["MISSING_ROWS"] = body_rows


    frames.append(r"""
\begin{frame}[plain]
\begin{tikzpicture}[remember picture,overlay]
\fill[navy] (current page.south west) rectangle (current page.north east);
\end{tikzpicture}
\vspace{2.2cm}
{\fontsize{20}{26}\selectfont\bfseries\color{white} __TITLE__\par}
\vspace{0.45cm}
{\color{white}\rule{6cm}{2pt}}
\vspace{0.55cm}

{\large\color{white} __SUBTITLE__\par}
\vspace{0.25cm}
{\small\color{white!70!navy} 报告 ID：__REPORT_ID__\quad·\quad 2026-11-24}\par
\end{frame}
""")

    overview_rows = "\n".join(
        f"{label} & {value} \\\\" for label, value in spec["overview"]
    )
    frames.append(r"""
\begin{frame}{评估概览}
\small
\begin{tabularx}{\textwidth}{>{\bfseries}p{2.2cm}X}
\toprule
\rowcolor{navy}\headrow{项目} & \headrow{内容} \\
\midrule
__OVERVIEW__ \\
\bottomrule
\end{tabularx}
\end{frame}
""")

    cost_items = []
    if cost.get("runtime_s") is not None:
        cost_items.append(f"运行时长 & {fmt(cost['runtime_s'], 1)} s / 条 \\\\")
    if cost.get("peak_memory_gb") is not None:
        cost_items.append(f"峰值显存 & {fmt(cost['peak_memory_gb'], 1)} GB / 卡 \\\\")
    if csd.get("csd_s") is not None:
        cost_items.append(f"CSD-S 风格一致性 $\\uparrow$ & {fmt(csd['csd_s'], 4)} \\\\")
    if csd.get("csd_c") is not None:
        cost_items.append(f"CSD-C 内容一致性 $\\uparrow$ & {fmt(csd['csd_c'], 4)} \\\\")
    cost_rows = "\n".join(cost_items)
    csd_rows = ""
    key_items = []
    key_items.append(("SSIM $\\uparrow$", f"{fmt(aggregate['ssim']['mean'], 4)} $\\pm$ {fmt(aggregate['ssim']['std'], 4)}"))
    key_items.append(("PSNR $\\uparrow$", f"{fmt(aggregate['psnr']['mean'], 2)} $\\pm$ {fmt(aggregate['psnr']['std'], 2)} dB"))
    if lang == "zh":
        flicker_label, warp_label = "亮度闪烁 $\\downarrow$", "重映射 RMSE $\\downarrow$"
        runtime_label, memory_label = "运行时长", "峰值显存"
        csd_s_label, csd_c_label = "CSD-S 风格一致性 $\\uparrow$", "CSD-C 内容一致性 $\\uparrow$"
    else:
        flicker_label, warp_label = "Luminance flicker $\\downarrow$", "Warp RMSE $\\downarrow$"
        runtime_label, memory_label = "Runtime", "Peak GPU memory"
        csd_s_label, csd_c_label = "CSD-S style consistency $\\uparrow$", "CSD-C content consistency $\\uparrow$"
    key_items.append((flicker_label, f"{fmt(aggregate['luminance_flicker']['mean'], 3)} $\\pm$ {fmt(aggregate['luminance_flicker']['std'], 3)}"))
    key_items.append((warp_label, f"{fmt(aggregate['offset_1_warp_rmse']['mean'], 2)} $\\pm$ {fmt(aggregate['offset_1_warp_rmse']['std'], 2)}"))
    if cost.get("runtime_s") is not None:
        key_items.append((runtime_label, f"{fmt(cost['runtime_s'], 1)} s / clip"))
    if cost.get("peak_memory_gb") is not None:
        key_items.append((memory_label, f"{fmt(cost['peak_memory_gb'], 1)} GB"))
    if csd.get("csd_s") is not None:
        key_items.append((csd_s_label, fmt(csd["csd_s"], 4)))
    if csd.get("csd_c") is not None:
        key_items.append((csd_c_label, fmt(csd["csd_c"], 4)))
    frames.append(r"""
\begin{frame}{关键结果}
\begin{columns}[T]
\begin{column}{0.52\textwidth}
\small
\begin{tabular}{lr}
\toprule
\rowcolor{navy}\headrow{指标} & \headrow{数值} \\
\midrule
__KEY_ROWS__
\bottomrule
\end{tabular}
\end{column}
\begin{column}{0.46\textwidth}
\small
\begin{itemize}
__KEY_BULLETS__
\end{itemize}
\end{column}
\end{columns}
\end{frame}
""")

    rows = []
    names = STYLE_ZH if lang == "zh" else STYLE_EN
    tag_names = TAG_ZH if lang == "zh" else TAG_EN
    best_style = max(order, key=lambda s: styles[s]["ssim"])
    worst_style = min(order, key=lambda s: styles[s]["ssim"])
    for style in order:
        value = styles[style]
        name = names.get(style, style)
        if style == best_style:
            prefix = r"\rowcolor{navy!15}"
            name = rf"\textbf{{{name}}}"
            ssim_cell = rf"\textbf{{{fmt(value['ssim'])}}}"
        elif style == worst_style:
            prefix = r"\rowcolor{blue!10}"
            ssim_cell = fmt(value["ssim"])
        else:
            prefix = ""
            ssim_cell = fmt(value["ssim"])
        rows.append(
            f"{prefix} {name} & {value['n']} & {ssim_cell} & {fmt(value['psnr'], 2)} & "
            f"{fmt(value['flicker'], 2)} & {fmt(value['warp'], 1)} \\\\"
        )
    table_font = r"\scriptsize" if len(order) > 6 else r"\small"

    frames.append(r"""
\begin{frame}{__STYLE_TITLE__}
__TABLE_FONT__
\begin{tabular}{lrrrrr}
\toprule
\rowcolor{navy}\headrow{风格} & \headrow{n} & \headrow{SSIM $\uparrow$} & \headrow{PSNR $\uparrow$} &
\headrow{闪烁 $\downarrow$} & \headrow{重映射 $\downarrow$} \\
\midrule
__STYLE_ROWS__
\bottomrule
\end{tabular}
\par\vspace{0.25em}
{\scriptsize\color{muted} __LEGEND__\par}
\end{frame}
""")

    if spec.get("chart"):
        chart_styles = sorted(order, key=lambda s: styles[s]["ssim"], reverse=True)
        best_index = chart_styles.index(best_style)
        worst_index = chart_styles.index(worst_style)
        others = " ".join(
            f"({fmt(styles[s]['ssim'])},{i})"
            for i, s in enumerate(chart_styles)
            if i not in (best_index, worst_index)
        )
        best_coord = f"({fmt(styles[best_style]['ssim'])},{best_index})"
        worst_coord = f"({fmt(styles[worst_style]['ssim'])},{worst_index})"
        coords = " ".join(
            f"({fmt(styles[s]['ssim'])},{i})" for i, s in enumerate(chart_styles)
        )
        labels = ", ".join(names.get(s, s) for s in chart_styles)
        extra["CHART_TICKS"] = ",".join(str(i) for i in range(len(chart_styles)))
        extra["CHART_HEIGHT"] = "0.78\\textheight" if len(chart_styles) > 6 else "0.40\\textheight"
        extra["CHART_OTHERS_PLOT"] = (
            f"\\addplot[fill=navy!70,draw=none] coordinates {{{others}}};" if others else ""
        )
        extra["BEST_COORD"] = best_coord
        extra["WORST_COORD"] = worst_coord
        frames.append(r"""
\begin{frame}{各风格 SSIM}
\begin{center}
\begin{tikzpicture}
\begin{axis}[
  xbar, width=0.92\textwidth, height=__CHART_HEIGHT__,
  xmin=0, xmax=0.68, bar width=10pt,
  ytick={__CHART_TICKS__},
  yticklabels={__CHART_LABELS__},
  yticklabel style={font=\scriptsize},
  y dir=reverse,
  nodes near coords, nodes near coords style={font=\scriptsize,color=ink},
  axis lines*=left, tick align=outside,
  xmajorgrids=true, grid style={black!12},
  enlarge y limits=0.06,
]
\addplot[fill=navy,draw=none] coordinates {__CHART_COORDS__};
\end{axis}
\end{tikzpicture}
\end{center}
{\scriptsize\color{muted} SSIM 越高越好；最优/最差已在上表标出。}
\end{frame}
""")
        extra["BEST_X"] = fmt(styles[best_style]["ssim"])
        extra["WORST_X"] = fmt(styles[worst_style]["ssim"])
        extra["BEST_I"] = best_index
        extra["WORST_I"] = worst_index

    tag_text = "；".join(
        f"{tag_names.get(k, k)} {v}" for k, v in sorted(tags.items(), key=lambda x: -x[1])
    )
    if lang == "zh":
        vlm_labels = [
            ("style_adherence", "风格遵循", "是否达到目标风格"),
            ("content_preservation", "内容保持", "主体与场景是否保留"),
            ("temporal_stability", "时序稳定", "闪烁与抖动"),
            ("artifact_control", "伪影控制", "纹理粘连、重影等"),
            ("overall_visual_quality", "整体质量", "综合偏好"),
        ]
    else:
        vlm_labels = [
            ("style_adherence", "Style adherence", "reaches the target style"),
            ("content_preservation", "Content preservation", "subject and scene retained"),
            ("temporal_stability", "Temporal stability", "flicker and jitter"),
            ("artifact_control", "Artifact control", "texture sticking, ghosting"),
            ("overall_visual_quality", "Overall quality", "holistic preference"),
        ]
    vlm_rows = "\n".join(
        f"{label} & {fmt(vlm[key], 2)} / 5 & {note} \\\\"
        for key, label, note in vlm_labels
    )
    if spec.get("comparison"):
        ghibli = styles.get("ghibli", {})
        van = styles.get("van_gogh", {})
        ssim_delta = ghibli.get("ssim", 0) - van.get("ssim", 0)
        flicker_delta = van.get("flicker", 0) - ghibli.get("flicker", 0)
        frames.append(r"""
\begin{frame}{关键对比}
\begin{columns}[T]
\begin{column}{0.5\textwidth}
\begin{center}
{\small\bfseries SSIM（越高越好）}
\begin{tikzpicture}
\begin{axis}[
  ybar, width=0.92\linewidth, height=0.36\textheight,
  ymin=0, ymax=0.68, bar width=26pt,
  symbolic x coords={吉卜力,梵高}, xtick=data,
  nodes near coords, nodes near coords style={font=\scriptsize,color=ink},
  axis lines*=left, ylabel={}, xmajorgrids=false, ymajorgrids=true,
  grid style={black!12}, enlarge x limits=0.25,
]
\addplot[fill=navy,draw=none] coordinates {(吉卜力,__G_SSIM__) (梵高,__V_SSIM__)};
\end{axis}
\end{tikzpicture}
\end{center}
\end{column}
\begin{column}{0.5\textwidth}
\begin{center}
{\small\bfseries 亮度闪烁（越低越好）}
\begin{tikzpicture}
\begin{axis}[
  ybar, width=0.92\linewidth, height=0.36\textheight,
  ymin=0, ymax=1.6, bar width=26pt,
  symbolic x coords={吉卜力,梵高}, xtick=data,
  nodes near coords, nodes near coords style={font=\scriptsize,color=ink},
  axis lines*=left, xmajorgrids=false, ymajorgrids=true,
  grid style={black!12}, enlarge x limits=0.25,
]
\addplot[fill=navy,draw=none] coordinates {(吉卜力,__G_FLICKER__) (梵高,__V_FLICKER__)};
\end{axis}
\end{tikzpicture}
\end{center}
\end{column}
\end{columns}
\vspace{0.25em}
\begin{center}
\colorbox{blue!12}{\small\bfseries SSIM 差距 +__SSIM_DELTA__} \qquad
\colorbox{blue!6}{\small\bfseries 闪烁差距 __FLICKER_DELTA__（吉卜力更低）}
\end{center}
\end{frame}
""")
        extra["G_SSIM"] = fmt(ghibli.get("ssim", 0))
        extra["V_SSIM"] = fmt(van.get("ssim", 0))
        extra["G_FLICKER"] = fmt(ghibli.get("flicker", 0), 2)
        extra["V_FLICKER"] = fmt(van.get("flicker", 0), 2)
        extra["SSIM_DELTA"] = fmt(ssim_delta)
        extra["FLICKER_DELTA"] = fmt(abs(flicker_delta), 2)

    if spec.get("vbench"):
        vbench = spec["vbench"]
        vbench_rows_list = []
        if lang == "zh":
            vbench_labels = [
                ("subject_consistency", "主体一致性", "越高越好"),
                ("background_consistency", "背景一致性", "越高越好"),
                ("temporal_flickering", "时序闪烁", "越高越好"),
                ("motion_smoothness", "运动平滑度", "越高越好"),
                ("aesthetic_quality", "美学质量", "越高越好"),
                ("imaging_quality", "成像质量", "越高越好"),
                ("dynamic_degree", "动态程度", "越接近 0.5 越好"),
            ]
        else:
            vbench_labels = [
                ("subject_consistency", "Subject consistency", "higher is better"),
                ("background_consistency", "Background consistency", "higher is better"),
                ("temporal_flickering", "Temporal flickering", "higher is better"),
                ("motion_smoothness", "Motion smoothness", "higher is better"),
                ("aesthetic_quality", "Aesthetic quality", "higher is better"),
                ("imaging_quality", "Imaging quality", "higher is better"),
                ("dynamic_degree", "Dynamic degree", "closer to 0.5"),
            ]
        for key, label, direction in vbench_labels:
            if vbench.get(key) is not None:
                vbench_rows_list.append(f"{label} & {fmt(vbench[key], 4)} & {direction} \\\\")
        frames.append(r"""
\begin{frame}{VBench 七维}
\small
\begin{tabular}{lrl}
\toprule
\rowcolor{navy}\headrow{维度} & \headrow{均分} & \headrow{方向} \\
\midrule
__VBENCH_ROWS__
\bottomrule
\end{tabular}
\par\vspace{0.3em}
{\scriptsize\color{muted} __VBENCH_NOTE__\par}
\end{frame}
""")
        extra["VBENCH_ROWS"] = "\n".join(vbench_rows_list)

    frames.append(r"""
\begin{frame}{定性评估（VLM）}
\small
\begin{tabular}{lrl}
\toprule
\rowcolor{navy}\headrow{维度} & \headrow{均分} & \headrow{说明} \\
\midrule
__VLM_ROWS__
\bottomrule
\end{tabular}
\par\vspace{0.5em}
{\footnotesize
\textbf{评审设置}\quad Qwen3-VL-Plus，单盲 contact sheet，每条只给目标风格。\par\vspace{0.2em}
\textbf{失败标签}\quad __TAG_TEXT__\par}
\end{frame}
""")

    if spec.get("image"):
      frames.append(r"""
\begin{frame}{示例}
\begin{center}
\includegraphics[width=0.96\textwidth]{__IMAGE__}
\end{center}
\vspace{-0.1cm}
{\scriptsize\color{muted} __IMAGE_CAPTION__}
\end{frame}
""")

    frames.append(r"""
\begin{frame}{结论与限制}
\small
\begin{itemize}
__CONCLUSION__
\end{itemize}
\end{frame}
""")

    frames.append(r"""
\begin{frame}[plain]
\begin{tikzpicture}[remember picture,overlay]
\fill[navy] (current page.south west) rectangle (current page.north east);
\end{tikzpicture}
\vspace{2.8cm}
\begin{center}
{\Huge\color{white} 谢谢！}
\end{center}
\end{frame}
""")

    missing_frames = [
        frame for frame in frames
        if "Missing metrics" in frame or "缺失指标及原因" in frame
    ]
    if missing_frames:
        frames = [frame for frame in frames if frame not in missing_frames]
        vlm_index = next(
            (
                index for index, frame in enumerate(frames)
                if "定性评估" in frame or "Qualitative assessment" in frame
            ),
            len(frames),
        )
        frames[vlm_index:vlm_index] = missing_frames

    values = {
        "TITLE": spec["title"],
        "SUBTITLE": spec["subtitle"],
        "REPORT_ID": report_id,
        "OVERVIEW": overview_rows,
        "SSIM": f"{fmt(aggregate['ssim']['mean'], 4)} $\\pm$ {fmt(aggregate['ssim']['std'], 4)}",
        "PSNR": f"{fmt(aggregate['psnr']['mean'], 2)} $\\pm$ {fmt(aggregate['psnr']['std'], 2)} dB",
        "FLICKER": f"{fmt(aggregate['luminance_flicker']['mean'], 3)} $\\pm$ {fmt(aggregate['luminance_flicker']['std'], 3)}",
        "WARP": f"{fmt(aggregate['offset_1_warp_rmse']['mean'], 2)} $\\pm$ {fmt(aggregate['offset_1_warp_rmse']['std'], 2)}",
        "COST": cost_rows,
        "CSD": csd_rows,
        "KEY_BULLETS": bullets(spec["key_bullets"]),
        "VBENCH_NOTE": (
            "VBench 0.1.5，custom\\_input 模式；分数已按 VBench 归一化。"
            if lang == "zh"
            else "VBench 0.1.5, custom\\_input mode; scores are normalised by VBench."
        ),
        "LEGEND": (
            "较深蓝底：SSIM 最优；较浅蓝底：SSIM 最差；SSIM 越高越好，闪烁与重映射越低越好。"
            if lang == "zh"
            else "Higher SSIM is better; best/worst are marked in the table."
        ),
        "KEY_ROWS": "\n".join(f"{label} & {value} \\\\" for label, value in key_items),
        "STYLE_TITLE": spec["style_title"],
        "TABLE_FONT": table_font,
        "STYLE_ROWS": "\n".join(rows),
        "VLM_ROWS": vlm_rows,
        "TAG_TEXT": tag_text or "无",
        "IMAGE": spec["image"],
        "IMAGE_CAPTION": spec["image_caption"],
        "CONCLUSION": bullets(spec["conclusion"]),
    }
    if spec.get("chart"):
        values["CHART_LABELS"] = labels
        values["CHART_COORDS"] = coords

    values.update(extra)
    body = fill(PREAMBLE, REPORT_ID=report_id)
    body += "\n\\begin{document}\n"
    body += "\n".join(fill(frame, **values) for frame in frames)
    body += "\n\\end{document}\n"
    if lang == "en":
        for zh, en in FIXED_EN.items():
            body = body.replace(zh, en)

    out_dir = Path(spec["out_dir"]) if spec.get("out_dir") else Path(spec["dir"]) / "slides"
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{spec['name']}_{lang}.tex"
    tex_path.write_text(body, encoding="utf-8")
    print("wrote", tex_path)
    return tex_path


def build_from_metrics(
    metrics_path: Path,
    review_path: Path,
    out_dir: Path,
    title: str = "视频风格迁移评估报告",
    subtitle: str | None = None,
    report_id: str | None = None,
    lang: str = "zh",
    image: str | None = None,
) -> Path:
    """Build a deck for an arbitrary evaluation directory."""
    metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    method_id = next(iter(metrics["aggregates"]))
    styles = style_stats(metrics, method_id)
    order = sorted(styles, key=lambda s: styles[s]["ssim"], reverse=True)
    count = len(metrics["cases"])
    experiment = metrics.get("experiment", {})
    labels = {
        m["id"]: m.get("label_zh") or m.get("label") or m["id"]
        for m in metrics.get("methods", [])
    }
    best = order[0]
    worst = order[-1]
    aggregate = metrics["aggregates"][method_id]

    cost: dict[str, float] = {}
    if aggregate.get("runtime_s"):
        cost["runtime_s"] = aggregate["runtime_s"]["mean"]
    if aggregate.get("peak_memory_gb"):
        cost["peak_memory_gb"] = aggregate["peak_memory_gb"]["mean"]
    csd = {
        key: aggregate[key]["mean"]
        for key in ("csd_s", "csd_c")
        if key in aggregate
    }
    vbench = {
        key.replace("vbench_", ""): aggregate[key]["mean"]
        for key in aggregate
        if key.startswith("vbench_")
    }

    contact_dir = Path(metrics_path).parent / "contact_sheets"
    images = sorted(contact_dir.glob("*.jpg")) if contact_dir.is_dir() else []
    image = image or (str(images[0].resolve()) if images else "")

    style_names = STYLE_ZH if lang == "zh" else STYLE_EN
    if lang == "zh":
        overview = [
            ("数据集", f"{count} 对（{len(styles)} 种风格）"),
            ("待评方法", "、".join(labels.values())),
            (
                "评估配置",
                f"seed {experiment.get('blind_seed', '—')} · 每视频 "
                f"{experiment.get('frame_limit', '—')} 帧 · 最大边 "
                f"{experiment.get('max_side', '—')} px",
            ),
            ("定性评审", "Qwen3-VL-Plus · 单盲 contact sheet"),
        ]
        key_bullets = [
            ("内容保持：", f"SSIM {fmt(aggregate['ssim']['mean'])} ± {fmt(aggregate['ssim']['std'])}。"),
            ("时序稳定：", f"亮度闪烁 {fmt(aggregate['luminance_flicker']['mean'], 2)}。"),
            ("风格差异：", f"{style_names.get(best, best)} 最好（{fmt(styles[best]['ssim'])}），"
                          f"{style_names.get(worst, worst)} 最差（{fmt(styles[worst]['ssim'])}）。"),
            ("样本：", f"{count} 对，方向一致的指标才可直接比较。"),
        ]
        conclusion = [
            ("最优风格：", f"{style_names.get(best, best)} 的 SSIM 为 {fmt(styles[best]['ssim'])}。"),
            ("最弱风格：", f"{style_names.get(worst, worst)} 的 SSIM 为 {fmt(styles[worst]['ssim'])}。"),
            ("时序：", f"平均亮度闪烁 {fmt(aggregate['luminance_flicker']['mean'], 2)}。"),
            ("限制：", "单方法评估；跨方法比较需在同一子集上运行基线。"),
        ]
        subtitle_text = subtitle or f"{count} 对 · {len(styles)} 种风格"
        style_title = "按风格结果"
        image_caption = "Contact sheet：源视频帧与盲化候选。"
    else:
        overview = [
            ("Dataset", f"{count} pairs ({len(styles)} styles)"),
            ("Method", ", ".join(labels.values())),
            (
                "Setup",
                f"seed {experiment.get('blind_seed', '—')} · "
                f"{experiment.get('frame_limit', '—')} frames per clip · "
                f"max side {experiment.get('max_side', '—')} px",
            ),
            ("Qualitative", "Qwen3-VL-Plus · single-blind contact sheets"),
        ]
        key_bullets = [
            ("Content:", f"SSIM {fmt(aggregate['ssim']['mean'])} ± {fmt(aggregate['ssim']['std'])}."),
            ("Temporal:", f"luminance flicker {fmt(aggregate['luminance_flicker']['mean'], 2)}."),
            ("Styles:", f"{style_names.get(best, best)} best ({fmt(styles[best]['ssim'])}), "
                        f"{style_names.get(worst, worst)} worst ({fmt(styles[worst]['ssim'])})."),
            ("Sample:", f"{count} pairs; compare only metrics with the same direction."),
        ]
        conclusion = [
            ("Best style:", f"{style_names.get(best, best)} reaches SSIM {fmt(styles[best]['ssim'])}."),
            ("Weakest style:", f"{style_names.get(worst, worst)} reaches SSIM {fmt(styles[worst]['ssim'])}."),
            ("Temporal:", f"mean luminance flicker {fmt(aggregate['luminance_flicker']['mean'], 2)}."),
            ("Limits:", "single method; baselines must run on the same subset."),
        ]
        subtitle_text = subtitle or f"{count} pairs · {len(styles)} styles"
        style_title = "Results by style"
        image_caption = "Contact sheet: source frames and blinded candidates."

    spec = {
        "name": Path(out_dir).name or "slides",
        "dir": Path(metrics_path).parents[1],
        "out_dir": str(out_dir),
        "metrics": metrics,
        "review": review,
        "method_id": method_id,
        "title": title,
        "subtitle": subtitle_text,
        "lang": lang,
        "report_id": report_id,
        "overview": overview,
        "style_order": order,
        "style_title": style_title,
        "chart": len(order) >= 2,
        "image": image,
        "image_caption": image_caption,
        "key_bullets": key_bullets,
        "conclusion": conclusion,
        "cost": cost,
        "csd": csd,
        "vbench": vbench,
    }
    return build(spec)


def _cli() -> None:
    import argparse
    import shutil
    import subprocess
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--title", default="视频风格迁移评估报告")
    parser.add_argument("--title-en", default="Video Style Transfer Evaluation Report")
    parser.add_argument("--subtitle", default=None)
    parser.add_argument("--report-id", default=None)
    parser.add_argument("--language", choices=["both", "zh", "en"], default="both")
    parser.add_argument("--image", default=None)
    args = parser.parse_args()

    languages = ["zh", "en"] if args.language == "both" else [args.language]
    tectonic = shutil.which("tectonic")
    for lang in languages:
        tex_path = build_from_metrics(
            args.metrics, args.review, args.out_dir,
            args.title if lang == "zh" else args.title_en,
            args.subtitle, args.report_id, lang,
            image=args.image,
        )
        if tectonic:
            result = subprocess.run(
                [tectonic, "-X", "compile", tex_path.name],
                cwd=tex_path.parent, capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                print(result.stdout[-800:])
                print(result.stderr[-800:])
                raise SystemExit(result.returncode)
            print("wrote", tex_path.with_suffix(".pdf"))
        else:
            print("tectonic not found; compile", tex_path, "manually")


if __name__ == "__main__":
    import sys

    if "--metrics" in sys.argv:
        _cli()
        raise SystemExit(0)

    base = Path("evaluation_run")
    runtime_values = json.loads(Path("/tmp/runtime.json").read_text())
    durations = [v for v in runtime_values.values() if 60 < v < 900]
    cost = {
        "runtime_s": statistics.mean(durations) if durations else None,
        "peak_memory_gb": None,
    }
    if Path("/tmp/mem_summary.json").is_file():
        cost["peak_memory_gb"] = json.loads(Path("/tmp/mem_summary.json").read_text())["peak_gb"]
    csd = json.loads(Path("/tmp/csd_summary.json").read_text()) if Path("/tmp/csd_summary.json").is_file() else {}

    build({
        "name": "reco_2style_10sample",
        "dir": base / "reco_2style_10sample",
        "title": "视频风格迁移评估报告",
        "subtitle": "ReCo-Bench 风格化子集 · 10 条视频 × 2 种风格（20 对）",
        "overview": [
            ("数据集", "ReCo-Bench stylization：10 条源视频 × 吉卜力 / 梵高（20 对）"),
            ("待评方法", "EchoStyle（Wan2.2-I2V-A14B + 双 LoRA）"),
            ("生成配置", "41 帧、832×480、16 fps、40 步、cfg 5.0"),
            ("评估配置", "seed 2026 · 41 帧 · 最大边 640 px · 偏移 [1, 5] · Farneback"),
            ("定性评审", "Qwen3-VL-Plus · 单盲 contact sheet"),
        ],
        "style_order": ["ghibli", "van_gogh"],
        "style_title": "按风格对比",
        "chart": False,
        "comparison": True,
        "key_bullets": [
            ("内容保持：", "吉卜力 SSIM 0.565，梵高 0.247。"),
            ("时序稳定：", "闪烁 0.68 vs 1.33。"),
            ("运动一致性：", "重映射误差 56.1 vs 56.8，接近。"),
            ("定位：", "20 对、41 帧、480p 的预览子集。"),
        ],
        "image": "../run/contact_sheets/reco_01_ghibli.jpg",
        "image_caption": "Contact sheet：源视频帧 + 吉卜力风格候选。",
        "conclusion": [
            ("客观指标：", "吉卜力内容保持与时序稳定更好（SSIM 0.565 vs 0.247；闪烁 0.68 vs 1.33）。"),
            ("VLM 感知：", "梵高风格遵循略高（4.5 vs 4.2），整体质量接近（3.9 vs 3.8）。"),
            ("运动一致性：", "重映射误差 56.1 vs 56.8，差异主要在外观与时序。"),
            ("限制：", "20 对、41 帧、832×480，不能与 81 帧/720p 混比。"),
        ],
        "cost": {},
        "csd": {},
    })

    build({
        "name": "reco_12style_5sample",
        "dir": base / "reco_12style_5sample",
        "title": "视频风格迁移评估报告",
        "subtitle": "ReCo-Bench 风格化子集 · 5 条视频 × 12 种风格（60 对）",
        "overview": [
            ("数据集", "ReCo-Bench stylization：前 5 条源视频 × 12 种风格（60 对）"),
            ("待评方法", "EchoStyle（Wan2.2-I2V-A14B + 双 LoRA）"),
            ("生成配置", "81 帧、1280×720、16 fps、40 步、cfg 5.0、8×H800"),
            ("评估配置", "seed 2026 · 81 帧 · 最大边 640 px · 偏移 [1, 5] · Farneback"),
            ("定性评审", "Qwen3-VL-Plus · 单盲 contact sheet"),
        ],
        "style_order": ["jojo", "watercolor", "monet", "ghibli", "simpsons", "3d_chibi",
                        "van_gogh", "irasutoya", "sketch", "american_cartoon",
                        "paper_cutting", "ukiyo_e"],
        "style_title": "按风格结果（12 种）",
        "chart": True,
        "key_bullets": [
            ("内容保持：", "SSIM 0.450 ± 0.178。"),
            ("时序稳定：", "闪烁 1.645，VLM 60/60 标记闪烁。"),
            ("运动一致性：", "重映射 RMSE 81.2。"),
            ("风格差异：", "JoJo 最好 0.576，浮世绘最差 0.264。"),
        ],
        "image": "../run/contact_sheets/3873059-hd_1920_1080_25fps__Ghibli.jpg",
        "image_caption": "Contact sheet：舞蹈视频的吉卜力风格候选。",
        "conclusion": [
            ("风格差异显著：", "JoJo 内容保持最好（0.576），浮世绘最差（0.264）。"),
            ("闪烁是主要问题：", "Ghibli 最高 3.49，水彩最低 1.00；VLM 60/60 标记闪烁。"),
            ("整体感知：", "风格遵循 4.38、内容 4.02，时序与伪影仅 3.00。"),
            ("限制：", "5 条视频、单方法、单评审模型；基线尚未运行。"),
        ],
        "cost": cost,
        "vbench": json.loads(Path("/tmp/vbench_summary.json").read_text()) if Path("/tmp/vbench_summary.json").is_file() else {},
        "csd": csd,
    })
