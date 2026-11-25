#!/usr/bin/env python3
"""Build paginated HTML slide decks from an evaluation run and print them to PDF."""

from __future__ import annotations

import argparse
import base64
import html
import json
import statistics
import subprocess
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

T = {
    "zh": {
        "title": "视频风格迁移评估报告",
        "overview": "评估概览",
        "key": "关键结果",
        "style": "各风格定量结果",
        "chart": "各风格 SSIM",
        "vbench": "VBench 七维",
        "missing": "缺失指标及原因",
        "vlm": "定性评估（VLM）",
        "example": "示例",
        "conclusion": "结论与限制",
        "thanks": "谢谢！",
        "item": "项目",
        "content": "内容",
        "metric": "指标",
        "value": "数值",
        "method": "方法",
        "style_label": "风格",
        "flicker": "闪烁 (gray)",
        "warp": "重映射 (RGB)",
        "dimension": "维度",
        "mean": "均分",
        "direction": "方向",
        "reason": "原因",
        "method_col": "方法",
        "report_id": "报告 ID",
        "dataset": "数据集",
        "setup": "评估配置",
        "qualitative": "定性评审",
        "gap": "缺口",
    },
    "en": {
        "title": "Video Style Transfer Evaluation Report",
        "overview": "Evaluation overview",
        "key": "Key results",
        "style": "Quantitative results by style",
        "chart": "SSIM by style",
        "vbench": "VBench (7 dimensions)",
        "missing": "Missing metrics and reasons",
        "vlm": "Qualitative assessment (VLM)",
        "example": "Example",
        "conclusion": "Conclusion and limitations",
        "thanks": "Thank you!",
        "item": "Item",
        "content": "Content",
        "metric": "Metric",
        "value": "Value",
        "method": "Method",
        "style_label": "Style",
        "flicker": "Flicker (gray)",
        "warp": "Warp (RGB)",
        "dimension": "Dimension",
        "mean": "Mean",
        "direction": "Direction",
        "reason": "Reason",
        "method_col": "Method",
        "report_id": "Report ID",
        "dataset": "Dataset",
        "setup": "Setup",
        "qualitative": "Qualitative review",
        "gap": "Gap",
    },
}

STYLE_ZH = {
    "ghibli": "吉卜力", "van_gogh": "梵高", "sketch": "素描", "watercolor": "水彩",
    "monet": "莫奈", "paper_cutting": "剪纸", "american_cartoon": "美式卡通",
    "irasutoya": "Irasutoya", "jojo": "JoJo", "ukiyo_e": "浮世绘",
    "simpsons": "辛普森", "3d_chibi": "3D Q 版",
}
STYLE_EN = {key: value for key, value in {
    "ghibli": "Ghibli", "van_gogh": "Van Gogh", "sketch": "Sketch", "watercolor": "Watercolor",
    "monet": "Monet", "paper_cutting": "Paper cutting", "american_cartoon": "American cartoon",
    "irasutoya": "Irasutoya", "jojo": "JoJo", "ukiyo_e": "Ukiyo-e",
    "simpsons": "Simpsons", "3d_chibi": "3D chibi",
}.items()}
TAG_ZH = {"flicker": "闪烁", "texture_sticking": "纹理粘连", "detail_loss": "细节损失",
          "geometry_melting": "几何融化", "color_bleed": "颜色渗漏", "edge_ghosting": "边缘重影"}
TAG_EN = {"flicker": "flicker", "texture_sticking": "texture sticking", "detail_loss": "detail loss",
          "geometry_melting": "geometry melting", "color_bleed": "colour bleed", "edge_ghosting": "edge ghosting"}

CSS = """
@page { size: 13.333in 7.5in; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: "PingFang SC", "Helvetica Neue", Arial, sans-serif; color: #17212b; background: #fff; }
.slide { width: 1280px; height: 720px; padding: 54px 64px 40px; page-break-after: always; position: relative; overflow: hidden; }
.slide:last-child { page-break-after: auto; }
.slide.dark { background: #002060; color: #fff; display: flex; flex-direction: column; justify-content: center; }
.slide.dark h1 { color: #fff; font-size: 46px; }
.slide.dark .sub { color: #d8e2f3; font-size: 22px; margin-top: 18px; }
.slide.dark .meta { color: #b9c8e4; font-size: 15px; margin-top: 26px; }
h1 { font-size: 34px; color: #002060; margin: 0 0 22px; font-weight: 700; }
h2 { font-size: 20px; color: #002060; margin: 20px 0 10px; }
table { width: 100%; border-collapse: collapse; font-size: 17px; }
th { text-align: left; background: #eef2f7; color: #002060; font-weight: 700; padding: 8px 10px; border-bottom: 1px solid #cbd6e4; }
td { padding: 7px 10px; border-bottom: 1px solid #e3e9f1; vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.two { display: flex; gap: 34px; align-items: flex-start; }
.two > div { flex: 1; }
.bullets { font-size: 18px; line-height: 1.5; }
.bullets li { margin-bottom: 8px; }
.bullets { padding-left: 20px; }
.footer { position: absolute; left: 64px; right: 64px; bottom: 18px; display: flex; justify-content: space-between;
          font-size: 12px; color: #7a8899; }
.bar-row { display: grid; grid-template-columns: 150px 1fr 70px; gap: 10px; align-items: center; font-size: 16px; margin-bottom: 8px; }
.bar-track { display: block; background: #eef2f7; height: 18px; border-radius: 4px; overflow: hidden; }
.bar-fill { display: block; background: #002060; height: 18px; }
.bar-fill.best { background: #1f4e9c; }
.bar-value { text-align: right; font-variant-numeric: tabular-nums; }
.note { font-size: 13px; color: #7a8899; margin-top: 8px; }
.tag { display: inline-block; background: #eef2f7; color: #002060; border-radius: 10px; padding: 2px 8px; margin: 2px 4px 2px 0; font-size: 13px; }
.figure { text-align: center; }
.figure img { max-width: 100%; max-height: 520px; border-radius: 10px; border: 1px solid #dbe2e9; }
.caption { font-size: 13px; color: #7a8899; margin-top: 10px; }
"""


def fmt(value, digits=3):
    return f"{value:.{digits}f}"


def esc(text):
    return html.escape(str(text))


def style_stats(metrics, method_id):
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


def review_stats(review):
    dims = ["style_adherence", "content_preservation", "temporal_stability",
            "artifact_control", "overall_visual_quality"]
    scores, tags = [], {}
    for entry in review["reviews"]:
        for score in entry["scores"]:
            scores.append(score)
            for tag in score.get("failure_tags", []):
                tags[tag] = tags.get(tag, 0) + 1
    return {d: statistics.mean(s[d] for s in scores) for d in dims}, tags


def slide(body, footer, index, total, cls="", report_id=""):
    footer_html = (
        f"<div class='footer'><span>{esc(report_id)}</span><span>{index} / {total}</span></div>"
        if cls != "dark"
        else ""
    )
    return f"<section class='slide {cls}'>{body}{footer_html}</section>"


def build(metrics_path, review_path, out_dir, title, title_en, report_id, lang):
    metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    method_id = next(iter(metrics["aggregates"]))
    aggregate = metrics["aggregates"][method_id]
    styles = style_stats(metrics, method_id)
    order = sorted(styles, key=lambda s: styles[s]["ssim"], reverse=True)
    names = STYLE_ZH if lang == "zh" else STYLE_EN
    tag_names = TAG_ZH if lang == "zh" else TAG_EN
    vlm, tags = review_stats(review)
    label = method_id if method_id != "echostyle" else "EchoStyle"
    count = len(metrics["cases"])
    experiment = metrics.get("experiment", {})
    t = T[lang]
    report_title = title if lang == "zh" else title_en
    total = 10

    cost = {}
    for key, out in (("runtime_s", "runtime"), ("peak_memory_gb", "memory")):
        if aggregate.get(key) and aggregate[key].get("mean") is not None:
            cost[out] = aggregate[key]["mean"]
    csd = {k: aggregate[k]["mean"] for k in ("csd_s", "csd_c") if aggregate.get(k)}
    vbench = {
        k.replace("vbench_", ""): aggregate[k]["mean"]
        for k in aggregate
        if k.startswith("vbench_")
    }

    slides = []
    # 1 title
    slides.append(slide(
        f"<h1>{esc(report_title)}</h1>"
        f"<div class='sub'>{count} {'对' if lang == 'zh' else 'pairs'} · {len(styles)} {'种风格' if lang == 'zh' else 'styles'}</div>"
        f"<div class='meta'>报告 ID / Report ID: {esc(report_id)} · 2026-11-24</div>",
        "", 1, total, "dark", report_id,
    ))

    # 2 overview
    rows = [
        (t["dataset"], f"{count} {'对' if lang == 'zh' else 'pairs'} · {len(styles)} {'种风格' if lang == 'zh' else 'styles'}"),
        (t["method"], label),
        (t["setup"], f"seed {experiment.get('blind_seed', '—')} · {experiment.get('frame_limit', '—')} frames · max side {experiment.get('max_side', '—')} px"),
        (t["qualitative"], "Qwen3-VL-Plus · single-blind contact sheets"),
    ]
    body = f"<h1>{t['overview']}</h1><table><thead><tr><th>{t['item']}</th><th>{t['content']}</th></tr></thead><tbody>"
    body += "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in rows)
    body += "</tbody></table>"
    slides.append(slide(body, "", 2, total, report_id=report_id))

    # 3 key results
    def mean(key, digits=3):
        value = aggregate.get(key)
        return fmt(value["mean"], digits) if value and value.get("mean") is not None else "—"

    key_rows = [
        ("CSD-S (cosine) ↑", mean("csd_s", 4)),
        ("SSIM (0–1) ↑", mean("ssim", 4)),
        ("PSNR (dB) ↑", mean("psnr", 2)),
        (f"{t['flicker']} ↓", mean("luminance_flicker", 2)),
        (f"{t['warp']} ↓", mean("offset_1_warp_rmse", 2)),
    ]
    if "runtime" in cost:
        key_rows.append((f"{'运行时长' if lang == 'zh' else 'Runtime'} (s/clip) ↓", fmt(cost["runtime"], 1)))
    if "memory" in cost:
        key_rows.append((f"{'峰值显存' if lang == 'zh' else 'Peak memory'} (GB) ↓", fmt(cost["memory"], 1)))
    table = f"<table><thead><tr><th>{t['metric']}</th><th class='num'>{t['value']}</th></tr></thead><tbody>"
    table += "".join(f"<tr><td>{esc(a)}</td><td class='num'>{esc(b)}</td></tr>" for a, b in key_rows)
    table += "</tbody></table>"
    bullets = [
        f"{'内容保持' if lang == 'zh' else 'Content'}: SSIM {fmt(aggregate['ssim']['mean'])} (0–1).",
        f"{'时序' if lang == 'zh' else 'Temporal'}: flicker {fmt(aggregate['luminance_flicker']['mean'], 2)} (gray levels).",
        f"{'风格差异' if lang == 'zh' else 'Styles'}: {names.get(order[0], order[0])} best ({fmt(styles[order[0]]['ssim'])}), {names.get(order[-1], order[-1])} worst ({fmt(styles[order[-1]]['ssim'])}).",
    ]
    body = f"<h1>{t['key']}</h1><div class='two'><div>{table}</div><div><ul class='bullets'>"
    body += "".join(f"<li>{esc(item)}</li>" for item in bullets) + "</ul></div></div>"
    slides.append(slide(body, "", 3, total, report_id=report_id))

    # 4 style table + 5 chart
    body = f"<h1>{t['style']}</h1><table><thead><tr><th>{t['style_label']}</th><th class='num'>n</th><th class='num'>SSIM (0–1) ↑</th><th class='num'>PSNR (dB) ↑</th><th class='num'>{t['flicker']} ↓</th><th class='num'>{t['warp']} ↓</th></tr></thead><tbody>"
    for idx, key in enumerate(order):
        value = styles[key]
        bold = " style='font-weight:700'" if idx in (0, len(order) - 1) else ""
        body += (
            f"<tr{bold}><td>{esc(names.get(key, key))}</td><td class='num'>{value['n']}</td>"
            f"<td class='num'>{fmt(value['ssim'])}</td><td class='num'>{fmt(value['psnr'], 2)}</td>"
            f"<td class='num'>{fmt(value['flicker'], 2)}</td><td class='num'>{fmt(value['warp'], 1)}</td></tr>"
        )
    body += "</tbody></table>"
    slides.append(slide(body, "", 4, total, report_id=report_id))

    max_ssim = max(styles[k]["ssim"] for k in order) or 1
    body = f"<h1>{t['chart']}</h1>"
    for idx, key in enumerate(order):
        value = styles[key]["ssim"]
        width = max(2, value / max_ssim * 100)
        cls = "best" if idx == 0 else ""
        body += (
            f"<div class='bar-row'><span>{esc(names.get(key, key))}</span>"
            f"<span class='bar-track'><span class='bar-fill {cls}' style='width:{width:.1f}%'></span></span>"
            f"<span class='bar-value'>{fmt(value)}</span></div>"
        )
    slides.append(slide(body, "", 5, total, report_id=report_id))

    # 6 VBench
    if vbench:
        labels = [
            ("subject_consistency", "主体一致性" if lang == "zh" else "Subject consistency"),
            ("background_consistency", "背景一致性" if lang == "zh" else "Background consistency"),
            ("temporal_flickering", "时序闪烁" if lang == "zh" else "Temporal flickering"),
            ("motion_smoothness", "运动平滑度" if lang == "zh" else "Motion smoothness"),
            ("aesthetic_quality", "美学质量" if lang == "zh" else "Aesthetic quality"),
            ("imaging_quality", "成像质量" if lang == "zh" else "Imaging quality"),
            ("dynamic_degree", "动态程度" if lang == "zh" else "Dynamic degree"),
        ]
        body = f"<h1>{t['vbench']}</h1><table><thead><tr><th>{t['dimension']}</th><th class='num'>{t['mean']}</th><th>{t['direction']}</th></tr></thead><tbody>"
        for key, name in labels:
            if key not in vbench:
                continue
            direction = ("越接近 0.5 越好" if key == "dynamic_degree" else "越高越好") if lang == "zh" else (
                "closer to 0.5" if key == "dynamic_degree" else "higher is better"
            )
            body += f"<tr><td>{esc(name)}</td><td class='num'>{fmt(vbench[key], 4)}</td><td>{esc(direction)}</td></tr>"
        body += "</tbody></table><div class='note'>VBench 0.1.5 · custom_input mode · scores normalised by VBench.</div>"
    else:
        body = f"<h1>{t['vbench']}</h1><p>{'本轮未运行 VBench。' if lang == 'zh' else 'VBench was not run.'}</p>"
    slides.append(slide(body, "", 6, total, report_id=report_id))

    # 7 missing
    missing = []
    if not any(case.get("style_image") for case in metrics["cases"]):
        missing.append(("LAB palette W1 / chroma W1", "no style reference image" if lang == "en" else "无风格参考图（文本驱动方法）"))
    if "runtime" not in cost:
        missing.append(("Runtime", "per-clip runtime not recorded" if lang == "en" else "未记录逐条推理耗时"))
    if "memory" not in cost:
        missing.append(("Peak GPU memory", "peak memory not sampled" if lang == "en" else "未采样峰值显存"))
    if not csd:
        missing.append(("CSD-S / CSD-C", "CSD evaluator not run" if lang == "en" else "未运行 CSD 外部评测器"))
    if not vbench:
        missing.append(("VBench dimensions", "VBench not run" if lang == "en" else "未运行 VBench"))
    body = f"<h1>{t['missing']}</h1><table><thead><tr><th>{t['metric']}</th><th>{t['reason']}</th></tr></thead><tbody>"
    body += "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in missing) or "<tr><td colspan='2'>—</td></tr>"
    body += "</tbody></table>"
    slides.append(slide(body, "", 7, total, report_id=report_id))

    # 8 VLM
    dims = [
        ("style_adherence", "风格遵循" if lang == "zh" else "Style adherence", "reaches the target style" if lang == "en" else "是否达到目标风格"),
        ("content_preservation", "内容保持" if lang == "zh" else "Content preservation", "subject and scene retained" if lang == "en" else "主体与场景是否保留"),
        ("temporal_stability", "时序稳定" if lang == "zh" else "Temporal stability", "flicker and jitter" if lang == "en" else "闪烁与抖动"),
        ("artifact_control", "伪影控制" if lang == "zh" else "Artifact control", "texture sticking, ghosting" if lang == "en" else "纹理粘连、重影等"),
        ("overall_visual_quality", "整体质量" if lang == "zh" else "Overall quality", "holistic preference" if lang == "en" else "综合偏好"),
    ]
    body = f"<h1>{t['vlm']}</h1><table><thead><tr><th>{t['dimension']}</th><th class='num'>{t['mean']}</th><th>{'说明' if lang == 'zh' else 'Description'}</th></tr></thead><tbody>"
    for key, name, note in dims:
        body += f"<tr><td>{esc(name)}</td><td class='num'>{fmt(vlm[key], 2)} / 5</td><td>{esc(note)}</td></tr>"
    body += "</tbody></table>"
    tag_text = " · ".join(f"{tag_names.get(k, k)} {v}" for k, v in sorted(tags.items(), key=lambda x: -x[1]))
    body += f"<div class='note'>{'评审设置' if lang == 'zh' else 'Review setup'}: Qwen3-VL-Plus · single-blind contact sheets.</div>"
    body += f"<div class='note'>{'失败标签' if lang == 'zh' else 'Failure tags'}: {esc(tag_text or '—')}</div>"
    slides.append(slide(body, "", 8, total, report_id=report_id))

    # 9 example
    contact_dir = Path(metrics_path).parent / "contact_sheets"
    images = sorted(contact_dir.glob("*.jpg"))
    if images:
        data = base64.b64encode(images[0].read_bytes()).decode("ascii")
        img = f"<img src='data:image/jpeg;base64,{data}' alt='contact sheet'>"
        caption = "Contact sheet：源视频帧与盲化候选。" if lang == "zh" else "Contact sheet: source frames and blinded candidates."
        body = f"<h1>{t['example']}</h1><div class='figure'>{img}<div class='caption'>{esc(caption)}</div></div>"
    else:
        body = f"<h1>{t['example']}</h1><p>No contact sheet.</p>"
    slides.append(slide(body, "", 9, total, report_id=report_id))

    # 10 conclusion
    def mean_or_dash(key, digits=3):
        value = aggregate.get(key)
        return fmt(value["mean"], digits) if value and value.get("mean") is not None else "—"

    conclusion = [
        ("风格模块" if lang == "zh" else "Style", f"CSD-S {mean_or_dash('csd_s', 3)} (cosine)"),
        ("内容模块" if lang == "zh" else "Content", f"SSIM {mean_or_dash('ssim')} (0–1), PSNR {mean_or_dash('psnr', 2)} dB"),
        ("时序与运动" if lang == "zh" else "Temporal and motion", f"flicker {mean_or_dash('luminance_flicker', 2)} (gray), warp {mean_or_dash('offset_1_warp_rmse', 2)} (RGB)"),
        ("成本" if lang == "zh" else "Cost", f"{fmt(cost.get('runtime', 0), 1)} s/clip, {fmt(cost.get('memory', 0), 1)} GB"),
        ("定性" if lang == "zh" else "Qualitative", f"VLM style {fmt(vlm['style_adherence'], 2)}, temporal {fmt(vlm['temporal_stability'], 2)} (1–5)"),
        ("限制" if lang == "zh" else "Limits", "single method, no cross-method ranking" if lang == "en" else "单方法结果，不构成跨方法排名"),
    ]
    body = f"<h1>{t['conclusion']}</h1><ul class='bullets'>"
    body += "".join(f"<li><b>{esc(head)}:</b> {esc(text)}</li>" for head, text in conclusion)
    body += "</ul>"
    slides.append(slide(body, "", 10, total, report_id=report_id))

    html_text = (
        "<!doctype html><html lang='%s'><head><meta charset='utf-8'>"
        "<title>%s</title><style>%s</style></head><body>%s</body></html>"
        % (lang, esc(report_title), CSS, "".join(slides))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"slides_{lang}.html"
    html_path.write_text(html_text, encoding="utf-8")
    pdf_path = out_dir / f"slides_{lang}.pdf"
    if Path(CHROME).is_file():
        subprocess.run(
            [CHROME, "--headless=new", "--no-pdf-header-footer",
             "--virtual-time-budget=8000", f"--print-to-pdf={pdf_path}",
             html_path.resolve().as_uri()],
            check=False, capture_output=True, text=True,
        )
    print("wrote", html_path, "and", pdf_path if pdf_path.is_file() else "(pdf failed)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--title", default="视频风格迁移评估报告")
    parser.add_argument("--title-en", default="Video Style Transfer Evaluation Report")
    parser.add_argument("--report-id", default="VST")
    parser.add_argument("--language", choices=["both", "zh", "en"], default="both")
    args = parser.parse_args()
    for lang in (["zh", "en"] if args.language == "both" else [args.language]):
        build(args.metrics, args.review, args.out_dir, args.title, args.title_en, args.report_id, lang)


if __name__ == "__main__":
    main()
