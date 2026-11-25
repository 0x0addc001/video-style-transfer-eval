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
\definecolor{gold}{RGB}{191,144,0}
\definecolor{ink}{RGB}{31,41,55}
\definecolor{muted}{RGB}{96,112,128}

\setbeamercolor{normal text}{fg=ink}
\setbeamercolor{frametitle}{fg=navy}
\setbeamercolor{structure}{fg=navy}
\setbeamercolor{footline}{fg=muted}
\setbeamertemplate{navigation symbols}{}
\setbeamertemplate{itemize item}{\color{gold}$\blacktriangleright$}
\setbeamerfont{frametitle}{size=\LARGE,series=\bfseries}
\setbeamerfont{title}{size=\Huge,series=\bfseries}
\setbeamertemplate{frametitle}{%
  \vspace{0.35em}\insertframetitle\par
  \vspace{0.15em}{\color{gold}\rule{\textwidth}{1.2pt}}%
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


def style_stats(metrics):
    per = {}
    for case in metrics["cases"]:
        record = case["methods"]["echostyle"]
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
    directory = Path(spec["dir"])
    metrics = json.loads((directory / "run" / "metrics.json").read_text(encoding="utf-8"))
    review_path = directory / "run" / "review_packet" / "validated_reviews.json"
    if not review_path.is_file():
        review_path = directory / "review_packet" / "validated_reviews.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    report_files = sorted((directory / "report").glob("report_zh_VST-*.pdf"))
    report_id = report_files[-1].stem.split("_")[2] if report_files else "VST"

    aggregate = metrics["aggregates"]["echostyle"]
    styles = style_stats(metrics)
    order = [s for s in spec["style_order"] if s in styles]
    vlm, tags = review_stats(review, metrics)
    cost = spec.get("cost", {})
    csd = spec.get("csd", {})

    frames = []
    extra: dict[str, object] = {}

    frames.append(r"""
\begin{frame}[plain]
\begin{tikzpicture}[remember picture,overlay]
\fill[navy] (current page.south west) rectangle (current page.north east);
\end{tikzpicture}
\vspace{2.2cm}
{\usebeamerfont{title}\color{white} __TITLE__\par}
\vspace{0.45cm}
{\color{gold}\rule{6cm}{2pt}}
\vspace{0.55cm}

{\large\color{white} __SUBTITLE__\par}
\vspace{0.25cm}
{\small\color{white!70!navy} 报告 ID：__REPORT_ID__\quad·\quad 2026-11-24}\par
\end{frame}
""")

    overview_rows = " \\\\\n".join(
        f"{label} & {value}" for label, value in spec["overview"]
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

    cost_rows = ""
    if cost.get("runtime_s") is not None:
        cost_rows += f"运行时长 & {fmt(cost['runtime_s'], 1)} s / 条 \\\\\n"
    if cost.get("peak_memory_gb") is not None:
        cost_rows += f"峰值显存 & {fmt(cost['peak_memory_gb'], 1)} GB / 卡 \\\\\n"
    vbench = spec.get("vbench", {})
    vbench_rows = ""
    for key, label in [
        ("subject_consistency", "VBench 主体一致 $\\uparrow$"),
        ("background_consistency", "VBench 背景一致 $\\uparrow$"),
        ("temporal_flickering", "VBench 时序闪烁 $\\uparrow$"),
        ("motion_smoothness", "VBench 运动平滑 $\\uparrow$"),
        ("aesthetic_quality", "VBench 美学 $\\uparrow$"),
        ("imaging_quality", "VBench 成像 $\\uparrow$"),
        ("dynamic_degree", "VBench 动态度 $\\rightarrow$"),
    ]:
        if vbench.get(key) is not None:
            vbench_rows += f"{label} & {fmt(vbench[key], 3)} \\\\\\n"
    csd_rows = ""
    if csd.get("csd_s") is not None:
        csd_rows += f"CSD-S 风格一致性 $\\uparrow$ & {fmt(csd['csd_s'], 4)} \\\\\n"
    if csd.get("csd_c") is not None:
        csd_rows += f"CSD-C 内容一致性 $\\uparrow$ & {fmt(csd['csd_c'], 4)} \\\\\n"

    frames.append(r"""
\begin{frame}{关键结果}
\begin{columns}[T]
\begin{column}{0.52\textwidth}
\small
\begin{tabular}{lr}
\toprule
\rowcolor{navy}\headrow{指标} & \headrow{数值} \\
\midrule
SSIM $\uparrow$ & __SSIM__ \\
PSNR $\uparrow$ & __PSNR__ \\
亮度闪烁 $\downarrow$ & __FLICKER__ \\
重映射 RMSE $\downarrow$ & __WARP__ \\
__COST____CSD__
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
    best_style = max(order, key=lambda s: styles[s]["ssim"])
    worst_style = min(order, key=lambda s: styles[s]["ssim"])
    for style in order:
        value = styles[style]
        name = STYLE_ZH.get(style, style)
        if style == best_style:
            prefix = r"\rowcolor{gold!22}"
            name = rf"\textbf{{{name}}}"
            ssim_cell = rf"\textbf{{{fmt(value['ssim'])}}}"
        elif style == worst_style:
            prefix = r"\rowcolor{red!8}"
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
{\scriptsize\color{muted} 金色底：SSIM 最优；红色底：SSIM 最差；SSIM 越高越好，闪烁与重映射越低越好。\par}
\end{frame}
""")

    if spec.get("chart"):
        chart_styles = sorted(order, key=lambda s: styles[s]["ssim"], reverse=True)
        coords = " ".join(
            f"({fmt(styles[s]['ssim'])},{i})" for i, s in enumerate(chart_styles)
        )
        labels = ", ".join(STYLE_ZH.get(s, s) for s in chart_styles)
        best_index = chart_styles.index(best_style)
        worst_index = chart_styles.index(worst_style)
        frames.append(r"""
\begin{frame}{各风格 SSIM}
\begin{center}
\begin{tikzpicture}
\begin{axis}[
  xbar, width=0.92\textwidth, height=0.78\textheight,
  xmin=0, xmax=0.68, bar width=10pt,
  ytick={0,...,11},
  yticklabels={__CHART_LABELS__},
  yticklabel style={font=\scriptsize},
  y dir=reverse,
  nodes near coords, nodes near coords style={font=\scriptsize,color=ink},
  axis lines*=left, tick align=outside,
  xmajorgrids=true, grid style={black!12},
  enlarge y limits=0.06,
]
\addplot[fill=navy,draw=none] coordinates {__CHART_COORDS__};
\addplot[fill=gold,draw=none] coordinates {(__BEST_X__,__BEST_I__)};
\addplot[fill=red!70,draw=none] coordinates {(__WORST_X__,__WORST_I__)};
\end{axis}
\end{tikzpicture}
\end{center}
{\scriptsize\color{muted} 金色：SSIM 最优；红色：SSIM 最差。}
\end{frame}
""")
        extra["BEST_X"] = fmt(styles[best_style]["ssim"])
        extra["WORST_X"] = fmt(styles[worst_style]["ssim"])
        extra["BEST_I"] = best_index
        extra["WORST_I"] = worst_index

    tag_text = "；".join(
        f"{TAG_ZH.get(k, k)} {v}" for k, v in sorted(tags.items(), key=lambda x: -x[1])
    )
    vlm_rows = " \\\\\n".join(
        f"{label} & {fmt(vlm[key], 2)} / 5 & {note}"
        for key, label, note in [
            ("style_adherence", "风格遵循", "是否达到目标风格"),
            ("content_preservation", "内容保持", "主体与场景是否保留"),
            ("temporal_stability", "时序稳定", "闪烁与抖动"),
            ("artifact_control", "伪影控制", "纹理粘连、重影等"),
            ("overall_visual_quality", "整体质量", "综合偏好"),
        ]
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
\addplot[fill=gold,draw=none] coordinates {(吉卜力,__G_SSIM__) (梵高,__V_SSIM__)};
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
\colorbox{gold!20}{\small\bfseries SSIM 差距 +__SSIM_DELTA__} \qquad
\colorbox{red!10}{\small\bfseries 闪烁差距 __FLICKER_DELTA__（吉卜力更低）}
\end{center}
\end{frame}
""")
        extra["G_SSIM"] = fmt(ghibli.get("ssim", 0))
        extra["V_SSIM"] = fmt(van.get("ssim", 0))
        extra["G_FLICKER"] = fmt(ghibli.get("flicker", 0), 2)
        extra["V_FLICKER"] = fmt(van.get("flicker", 0), 2)
        extra["SSIM_DELTA"] = fmt(ssim_delta)
        extra["FLICKER_DELTA"] = fmt(abs(flicker_delta), 2)

    frames.append(r"""
\begin{frame}{定性评估（VLM）}
\small
\begin{columns}[T]
\begin{column}{0.56\textwidth}
\begin{tabular}{lrl}
\toprule
\rowcolor{navy}\headrow{维度} & \headrow{均分} & \headrow{说明} \\
\midrule
__VLM_ROWS__ \\
\bottomrule
\end{tabular}
\end{column}
\begin{column}{0.40\textwidth}
\footnotesize
\textbf{评审设置}\par
Qwen3-VL-Plus，单盲 contact sheet，每条只给目标风格。\par\medskip
\textbf{失败标签}\par
__TAG_TEXT__
\end{column}
\end{columns}
\end{frame}
""")

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
        "CSD": csd_rows + vbench_rows,
        "KEY_BULLETS": bullets(spec["key_bullets"]),
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

    out_dir = Path(spec["dir"]) / "slides"
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{spec['name']}.tex"
    tex_path.write_text(body, encoding="utf-8")
    print("wrote", tex_path)
    return tex_path


if __name__ == "__main__":
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
        "cost": cost,
        "csd": csd,
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
        "csd": csd,
    })
