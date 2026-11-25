#!/usr/bin/env python3
"""Build a Chinese result deck from an evaluation directory and its template."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

NAVY = RGBColor(0x00, 0x20, 0x60)
GOLD = RGBColor(0xBF, 0x90, 0x00)
INK = RGBColor(0x1F, 0x29, 0x37)
MUTED = RGBColor(0x55, 0x63, 0x73)
LIGHT = RGBColor(0xF3, 0xF5, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT_CN = "PingFang SC"

STYLE_ZH = {
    "ghibli": "吉卜力",
    "van_gogh": "梵高",
    "sketch": "素描",
    "watercolor": "水彩",
    "monet": "莫奈",
    "paper_cutting": "剪纸",
    "american_cartoon": "美式卡通",
    "irasutoya": "Irasutoya",
    "jojo": "JoJo",
    "ukiyo_e": "浮世绘",
    "simpsons": "辛普森",
    "3d_chibi": "3D Q 版",
}


def set_run(run, size, bold=False, color=INK, font=FONT_CN):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font


def add_text(slide, text, x, y, w, h, size=16, bold=False, color=INK,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    for index, line in enumerate(text.split("\n")):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = align
        run = paragraph.add_run()
        run.text = line
        set_run(run, size, bold, color)
    return box


def add_bullets(slide, items, x, y, w, h, size=16):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    for index, (head, body) in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.space_after = Pt(8)
        run = paragraph.add_run()
        run.text = "• "
        set_run(run, size, True, NAVY)
        run = paragraph.add_run()
        run.text = head
        set_run(run, size, True, NAVY)
        if body:
            run = paragraph.add_run()
            run.text = body
            set_run(run, size, False, INK)
    return box


def add_table(slide, data, x, y, w, h, col_widths=None, font_size=12,
              highlights=None, header_size=None, center_body=False):
    highlights = highlights or set()
    rows, cols = len(data), len(data[0])
    shape = slide.shapes.add_table(rows, cols, Inches(x), Inches(y), Inches(w), Inches(h))
    table = shape.table
    if col_widths:
        for index, width in enumerate(col_widths):
            table.columns[index].width = Inches(width)
    for r, row in enumerate(data):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.08)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            frame = cell.text_frame
            frame.word_wrap = True
            paragraph = frame.paragraphs[0]
            paragraph.alignment = (
                PP_ALIGN.CENTER if (c and center_body) or c == 0 else PP_ALIGN.LEFT
            )
            run = paragraph.add_run()
            run.text = str(value)
            if r == 0:
                set_run(run, header_size or font_size, True, WHITE)
                cell.fill.solid()
                cell.fill.fore_color.rgb = NAVY
            else:
                bold = (r - 1) in highlights
                set_run(run, font_size, bold, NAVY if bold else INK)
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(0xFB, 0xF7, 0xEA) if bold else (
                    LIGHT if r % 2 == 0 else WHITE
                )
    return table


def add_bar_chart(slide, categories, values, x, y, w, h, number_format="0.000",
                  highlight_index=None):
    data = CategoryChartData()
    data.categories = categories
    data.add_series("SSIM", values)
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), data
    ).chart
    chart.has_legend = False
    chart.has_title = False
    plot = chart.plots[0]
    plot.gap_width = 45
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.number_format = number_format
    labels.number_format_is_linked = False
    labels.position = XL_LABEL_POSITION.OUTSIDE_END
    labels.font.size = Pt(10)
    labels.font.color.rgb = INK
    series = plot.series[0]
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = NAVY
    if highlight_index is not None:
        point = series.points[highlight_index]
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = GOLD
    chart.category_axis.tick_labels.font.size = Pt(11)
    chart.category_axis.tick_labels.font.color.rgb = INK
    chart.value_axis.tick_labels.font.size = Pt(9)
    chart.value_axis.has_major_gridlines = True
    chart.value_axis.maximum_scale = max(values) * 1.18
    chart.value_axis.minimum_scale = 0
    return chart


def slide_number(slide, index, total, report_id):
    add_text(slide, str(index), 12.45, 7.06, 0.4, 0.3, size=10, color=MUTED, align=PP_ALIGN.RIGHT)
    add_text(slide, report_id, 0.6, 7.06, 7.0, 0.3, size=9, color=MUTED)


def content_slide(prs, title, index, total, report_id):
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    for placeholder in slide.placeholders:
        placeholder.text = ""
    heading = slide.shapes.title if slide.shapes.title is not None else None
    if heading is None:
        for placeholder in slide.placeholders:
            if placeholder.placeholder_format.idx == 11:
                heading = placeholder
                break
    frame = heading.text_frame
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    run = paragraph.add_run()
    run.text = title
    set_run(run, 26, True, NAVY, "Times New Roman")
    slide_number(slide, index, total, report_id)
    return slide


def style_stats(metrics):
    per_style = {}
    for case in metrics["cases"]:
        record = case["methods"]["echostyle"]
        if not record.get("valid"):
            continue
        key = case["style_id"].lower().replace(" ", "_").replace("-", "_")
        per_style.setdefault(key, []).append(record["metrics"])
    rows = {}
    for style, values in per_style.items():
        rows[style] = {
            "n": len(values),
            "ssim": statistics.mean(v["ssim"] for v in values),
            "psnr": statistics.mean(v["psnr"] for v in values),
            "flicker": statistics.mean(v["luminance_flicker"] for v in values),
            "warp": statistics.mean(v["offset_1_warp_rmse"] for v in values),
        }
    return rows


def review_stats(review, metrics):
    blind_map = review["blind_map"]
    style_of = {
        case["id"]: case["style_id"].lower().replace(" ", "_").replace("-", "_")
        for case in metrics["cases"]
    }
    dims = ["style_adherence", "content_preservation", "temporal_stability",
            "artifact_control", "overall_visual_quality"]
    scores = []
    by_style = {}
    tags = {}
    for entry in review["reviews"]:
        for score in entry["scores"]:
            scores.append(score)
            style = style_of.get(score["case_id"])
            if style:
                by_style.setdefault(style, []).append(score)
            for tag in score.get("failure_tags", []):
                tags[tag] = tags.get(tag, 0) + 1
    overall = {d: statistics.mean(s[d] for s in scores) for d in dims} if scores else {}
    style_means = {
        style: {d: statistics.mean(s[d] for s in items) for d in dims}
        for style, items in by_style.items()
    }
    return overall, style_means, tags


def build(spec):
    directory = Path(spec["dir"])
    metrics = json.loads((directory / "run" / "metrics.json").read_text(encoding="utf-8"))
    review_path = directory / "run" / "review_packet" / "validated_reviews.json"
    if not review_path.is_file():
        review_path = directory / "review_packet" / "validated_reviews.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    report_files = sorted((directory / "report").glob("report_zh_VST-*.pdf"))
    report_id = report_files[-1].stem.split("_")[2] if report_files else "VST"

    aggregate = metrics["aggregates"]["echostyle"]
    overall_vlm, style_vlm, tags = review_stats(review, metrics)
    styles = style_stats(metrics)
    order = spec["style_order"]
    styles_present = [s for s in order if s in styles]

    prs = Presentation(directory / "template.pptx")
    # drop the template thank-you slide; it is re-added at the end
    sld_ids = list(prs.slides._sldIdLst)
    last = sld_ids[-1]
    prs.part.drop_rel(last.rId)
    prs.slides._sldIdLst.remove(last)
    # the template's demo content slide is replaced by generated slides
    demo = list(prs.slides._sldIdLst)[1]
    prs.part.drop_rel(demo.rId)
    prs.slides._sldIdLst.remove(demo)

    cover = prs.slides[0]
    cover_placeholders = sorted(cover.placeholders, key=lambda ph: ph.placeholder_format.idx)
    for placeholder in cover.placeholders:
        placeholder.text = ""
    title_ph = cover_placeholders[0]
    title_ph.text_frame.word_wrap = True
    run = title_ph.text_frame.paragraphs[0].add_run()
    run.text = spec["title"]
    set_run(run, 32, True, NAVY, "Times New Roman")
    subtitle_ph = cover_placeholders[1]
    subtitle_ph.left = Inches(1.1)
    subtitle_ph.width = Inches(11.1)
    subtitle_ph.top = Inches(3.95)
    subtitle_ph.height = Inches(1.4)
    paragraph = subtitle_ph.text_frame.paragraphs[0]
    for index, line in enumerate(spec["subtitle"]):
        target = paragraph if index == 0 else subtitle_ph.text_frame.add_paragraph()
        target.alignment = PP_ALIGN.CENTER
        run = target.add_run()
        run.text = line
        set_run(run, 15 if index == 0 else 12.5, index == 0, NAVY, FONT_CN)
    for shape in list(cover.shapes):
        if shape.name == "组合 7":
            shape._element.getparent().remove(shape._element)

    total = spec["total_slides"]
    index = 2

    slide = content_slide(prs, "评估概览", index, total, report_id)
    overview = spec["overview"]
    add_table(slide, [["项目", "内容"]] + overview, 0.6, 1.25, 12.1, 0.55 + 0.62 * len(overview),
              col_widths=[2.3, 9.8], font_size=13, center_body=False)
    index += 1

    slide = content_slide(prs, "关键结果", index, total, report_id)
    key_rows = [
        ["指标", "数值", "偏好"],
        ["SSIM", f"{aggregate['ssim']['mean']:.4f} ± {aggregate['ssim']['std']:.4f}", "越高越好"],
        ["PSNR", f"{aggregate['psnr']['mean']:.2f} ± {aggregate['psnr']['std']:.2f} dB", "越高越好"],
        ["亮度闪烁", f"{aggregate['luminance_flicker']['mean']:.3f} ± {aggregate['luminance_flicker']['std']:.3f}", "越低越好"],
        ["重映射 RMSE Δ1", f"{aggregate['offset_1_warp_rmse']['mean']:.2f} ± {aggregate['offset_1_warp_rmse']['std']:.2f}", "越低越好"],
    ]
    add_table(slide, key_rows, 0.6, 1.3, 7.2, 3.6, col_widths=[2.4, 3.4, 1.4], font_size=14,
              center_body=True)
    add_bullets(slide, spec["key_bullets"], 8.1, 1.35, 4.6, 4.6, size=14)
    index += 1

    slide = content_slide(prs, spec["style_slide_title"], index, total, report_id)
    rows = [["风格", "n", "SSIM ↑", "PSNR ↑", "闪烁 ↓", "重映射 ↓"]]
    best = max(styles_present, key=lambda s: styles[s]["ssim"])
    worst = min(styles_present, key=lambda s: styles[s]["ssim"])
    highlight = {styles_present.index(best), styles_present.index(worst)}
    for style in styles_present:
        value = styles[style]
        rows.append([
            STYLE_ZH.get(style, style), value["n"],
            f"{value['ssim']:.3f}", f"{value['psnr']:.2f}",
            f"{value['flicker']:.2f}", f"{value['warp']:.1f}",
        ])
    dense = len(styles_present) > 8
    row_height = 0.40 if dense else 0.46
    table_height = 0.5 + row_height * len(styles_present)
    add_table(slide, rows, 0.6, 1.2, 7.4, table_height,
              col_widths=[1.6, 0.6, 1.2, 1.2, 1.2, 1.4],
              font_size=10.5 if dense else (12 if len(styles_present) > 6 else 14),
              highlights=highlight)
    chart_styles = sorted(styles_present, key=lambda s: styles[s]["ssim"], reverse=True)
    add_bar_chart(
        slide, [STYLE_ZH.get(s, s) for s in chart_styles],
        [styles[s]["ssim"] for s in chart_styles],
        8.2, 1.2, 4.5, 5.4,
        highlight_index=0 if chart_styles else None,
    )
    index += 1

    slide = content_slide(prs, "定性评估（VLM）", index, total, report_id)
    vlm_rows = [["维度", "均分", "说明"]]
    labels = [
        ("style_adherence", "风格遵循", "是否达到目标风格"),
        ("content_preservation", "内容保持", "主体与场景是否保留"),
        ("temporal_stability", "时序稳定", "闪烁与抖动"),
        ("artifact_control", "伪影控制", "纹理粘连、重影等"),
        ("overall_visual_quality", "整体质量", "综合偏好"),
    ]
    for key, label, note in labels:
        vlm_rows.append([label, f"{overall_vlm[key]:.2f} / 5", note])
    add_table(slide, vlm_rows, 0.6, 1.25, 7.2, 3.4, col_widths=[2.0, 1.8, 3.4], font_size=14)
    tag_text = "；".join(f"{spec['tag_zh'].get(k, k)} {v}" for k, v in sorted(tags.items(), key=lambda x: -x[1]))
    add_bullets(slide, [
        ("评审设置：", "Qwen3-VL-Plus，单盲 contact sheet，每条只给目标风格。"),
        ("失败标签：", tag_text or "无"),
    ], 8.1, 1.3, 4.7, 4.8, size=13)
    index += 1

    slide = content_slide(prs, "示例", index, total, report_id)
    image = Path(spec["image"])
    slide.shapes.add_picture(str(image), Inches(0.6), Inches(1.3), width=Inches(12.1))
    add_text(slide, spec["image_caption"], 0.6, 6.55, 12.1, 0.4, size=11, color=MUTED)
    index += 1

    slide = content_slide(prs, "结论与限制", index, total, report_id)
    add_bullets(slide, spec["conclusion"], 0.7, 1.35, 11.9, 5.4, size=15)

    for shape in prs.slide_layouts[2].shapes:
        if shape.has_text_frame and "Thanks" in shape.text:
            run = shape.text_frame.paragraphs[0].runs[0]
            run.text = "谢谢！"
            run.font.name = FONT_CN
    thanks = prs.slides.add_slide(prs.slide_layouts[2])

    output = directory / "report" / f"report_{report_id}_slides.pptx"
    prs.save(output)
    print("wrote", output, "slides", len(prs.slides))


if __name__ == "__main__":
    base = Path("evaluation_run")
    build({
        "dir": base / "reco_2style_10sample",
        "title": "视频风格迁移评估报告",
        "subtitle": [
            "ReCo-Bench 风格化子集 · 10 条视频 × 2 种风格（20 对）",
            "报告 ID：VST-20261124T203838-472e93301264 · 2026-11-24",
        ],
        "total_slides": 8,
        "style_order": ["ghibli", "van_gogh"],
        "style_slide_title": "按风格对比",
        "overview": [
            ["数据集", "ReCo-Bench stylization：10 条源视频 × 吉卜力 / 梵高（20 对）"],
            ["待评方法", "EchoStyle（Wan2.2-I2V-A14B + 双 LoRA）"],
            ["生成配置", "41 帧、832×480、16 fps、40 步、cfg 5.0"],
            ["评估配置", "seed 2026 · 每视频 41 帧 · 最大边 640 px · 偏移 [1, 5] · Farneback 光流"],
            ["定性评审", "Qwen3-VL-Plus · 单盲 contact sheet，每条带目标风格"],
            ["报告 ID", "VST-20261124T203838-472e93301264"],
        ],
        "key_bullets": [
            ("按风格看内容保持：", "吉卜力 SSIM 0.565 vs 梵高 0.247，PSNR 12.73 vs 10.93。"),
            ("按风格看时序稳定：", "吉卜力闪烁 0.68 vs 梵高 1.33，梵高约差一倍。"),
            ("运动一致性接近：", "重映射误差 56.1 vs 56.8，风格差异小于风格化本身的影响。"),
            ("定位：", "20 对 · 41 帧 · 480p 的预览子集，不可与 81 帧/720p 全量比较。"),
        ],
        "tag_zh": {"flicker": "闪烁", "texture_sticking": "纹理粘连", "detail_loss": "细节损失",
                   "geometry_melting": "几何融化", "color_bleed": "颜色渗漏"},
        "image": base / "reco_2style_10sample" / "run" / "contact_sheets" / "reco_01_ghibli.jpg",
        "image_caption": "Contact sheet 示例：源视频帧 + 盲化候选（吉卜力）。",
        "conclusion": [
            ("客观指标：", "吉卜力内容保持与时序稳定明显更好（SSIM 0.565 vs 0.247；闪烁 0.68 vs 1.33）。"),
            ("VLM 感知：", "梵高风格遵循略高（4.5 vs 4.2），整体质量接近（3.9 vs 3.8）。"),
            ("运动一致性接近：", "重映射误差 56.1 vs 56.8，差异主要在外观保持与时序稳定性。"),
            ("限制：", "20 对、41 帧、832×480、仅 2 种风格；不能与 81 帧/720p 结果混比。"),
        ],
    })
    build({
        "dir": base / "reco_12style_5sample",
        "title": "视频风格迁移评估报告",
        "subtitle": [
            "ReCo-Bench 风格化子集 · 5 条视频 × 12 种风格（60 对）",
            "报告 ID：VST-20261124T223913-4d29c0ba0b8f · 2026-11-24",
        ],
        "total_slides": 8,
        "style_order": ["jojo", "watercolor", "monet", "ghibli", "simpsons", "3d_chibi",
                        "van_gogh", "irasutoya", "sketch", "american_cartoon",
                        "paper_cutting", "ukiyo_e"],
        "style_slide_title": "按风格结果（12 种）",
        "overview": [
            ["数据集", "ReCo-Bench stylization：前 5 条源视频 × 12 种风格（60 对）"],
            ["待评方法", "EchoStyle（Wan2.2-I2V-A14B + 双 LoRA）"],
            ["生成配置", "81 帧、1280×720、16 fps、40 步、cfg 5.0、8×H800"],
            ["评估配置", "seed 2026 · 每视频 81 帧 · 最大边 640 px · 偏移 [1, 5] · Farneback 光流"],
            ["定性评审", "Qwen3-VL-Plus · 单盲 contact sheet，每条带目标风格"],
            ["报告 ID", "VST-20261124T223913-4d29c0ba0b8f"],
        ],
        "key_bullets": [
            ("SSIM 0.450 ± 0.178：", "内容结构在风格化后保留约一半。"),
            ("PSNR 12.27 dB：", "像素级差异大，属风格迁移常态。"),
            ("闪烁 1.65：", "VLM 对 60/60 条都标记了闪烁。"),
            ("重映射 RMSE 81.2：", "运动一致性仍有明显损失。"),
        ],
        "tag_zh": {"flicker": "闪烁", "texture_sticking": "纹理粘连", "detail_loss": "细节损失",
                   "geometry_melting": "几何融化", "color_bleed": "颜色渗漏", "edge_ghosting": "边缘重影"},
        "image": base / "reco_12style_5sample" / "run" / "contact_sheets" /
                 "3873059-hd_1920_1080_25fps__Ghibli.jpg",
        "image_caption": "Contact sheet 示例：舞蹈视频的吉卜力风格化候选。",
        "conclusion": [
            ("风格差异显著：", "JoJo 内容保持最好（0.576），浮世绘最差（0.264）。"),
            ("闪烁是主要问题：", "Ghibli 闪烁最高（3.49），水彩最低（1.00）；VLM 60/60 标记闪烁。"),
            ("整体感知：", "风格遵循 4.38、内容 4.02，但时序与伪影仅 3.00。"),
            ("限制：", "5 条视频、单方法、单评审模型；基线尚未在 60 对上运行。"),
        ],
    })
