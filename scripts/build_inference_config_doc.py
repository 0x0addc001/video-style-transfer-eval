#!/usr/bin/env python3
"""Generate the English inference-split configuration document (DOCX)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evaluation_run" / "reco_12style_5sample"
OUT_DOCX = ROOT / "docs" / "echostyle-inference-split.docx"

NAVY = RGBColor(0x00, 0x20, 0x60)
GREY = RGBColor(0x5A, 0x67, 0x78)
FONT = "Calibri"


def shade(cell, color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tc_pr.append(shd)


def heading(doc, text: str, level: int = 1):
    paragraph = doc.add_heading(level=level)
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.color.rgb = NAVY
    run.font.bold = True
    run.font.size = Pt(16 if level == 1 else 12.5)
    paragraph.paragraph_format.space_before = Pt(14 if level == 1 else 10)
    paragraph.paragraph_format.space_after = Pt(6)
    return paragraph


def para(doc, text: str, size: float = 10.5, bold: bool = False, color=None):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(5)
    paragraph.paragraph_format.line_spacing = 1.15
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    return paragraph


def bullet(doc, text: str):
    paragraph = doc.add_paragraph(style="List Bullet")
    paragraph.paragraph_format.space_after = Pt(3)
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(10.5)
    return paragraph


def code(doc, text: str):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Cm(0.4)
    paragraph.paragraph_format.space_after = Pt(6)
    run = paragraph.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x1B, 0x24, 0x33)


def table(doc, rows, widths=None, font_size=9.5):
    table_obj = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table_obj.style = "Table Grid"
    table_obj.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r, row in enumerate(rows):
        tr_pr = table_obj.rows[r]._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        tr_pr.append(cant_split)
        if r == 0:
            header = OxmlElement("w:tblHeader")
            tr_pr.append(header)
        for c, value in enumerate(row):
            cell = table_obj.cell(r, c)
            cell.text = ""
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(2)
            run = paragraph.add_run(str(value))
            run.font.name = FONT
            run.font.size = Pt(font_size)
            run.font.bold = r == 0
            if r == 0:
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                shade(cell, "002060")
            elif r % 2 == 0:
                shade(cell, "EEF3FA")
    if widths:
        for index, width in enumerate(widths):
            for row in table_obj.rows:
                row.cells[index].width = Cm(width)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table_obj


def main() -> None:
    metrics = json.loads((RUN / "evaluation" / "metrics.json").read_text(encoding="utf-8"))
    manifest = json.loads((RUN / "inputs" / "manifest.json").read_text(encoding="utf-8"))
    cases = manifest["cases"]
    content_ids = sorted({case["content_id"] for case in cases})
    styles = sorted({case["style_id"] for case in cases})

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)

    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10.5)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = title.add_run("EchoStyle on ReCo-Bench — Shared Inference Configuration")
    run.font.name = FONT
    run.font.size = Pt(24)
    run.font.bold = True
    run.font.color.rgb = NAVY
    para(
        doc,
        "English configuration sheet for splitting the 60-pair (5 videos × 12 styles) inference run. "
        "Please mirror the items marked MUST MATCH; the remaining items can differ as long as they are reported.",
        size=11,
        color=GREY,
    )
    para(doc, f"Version 1.0 · {dt.date.today().isoformat()} · Prepared by: [your name] · Contact: [email/Slack]", size=9, color=GREY)

    heading(doc, "1. At a glance")
    table(
        doc,
        [
            ["Item", "Value"],
            ["Task", "EchoStyle inference on ReCo-Bench subset5"],
            ["Pairs", "60 = 5 source videos × 12 artistic styles"],
            ["Hardware", "8× NVIDIA H800 80 GB (HKUST SuperPOD, account mscaisuperpod)"],
            ["Model", "EchoStyle (ECCV 2026), 14B Wan2.2 DiT, FSDP + Ulysses, CUDA-only"],
            ["Resolution / frames", "1280×720 · 81 frames per clip · seed 2026 (method seed 42)"],
            ["Measured cost (my node)", "266.1 s/clip · 75.8 GB peak GPU memory"],
            ["Evaluation", "I run diagnostics, VBench, CSD, VLM review and the report centrally"],
        ],
        widths=[4.8, 12.0],
        font_size=9.5,
    )

    heading(doc, "2. Hardware and environment")
    bullet(doc, "GPU: 8× NVIDIA H800 80 GB, single node. EchoStyle's 14B Wan2.2 DiT uses FSDP + Ulysses and is CUDA-only.")
    bullet(doc, "Account: HKUST SuperPOD account mscaisuperpod; billing HKD 0.20 per GPU-minute (HKD 12 per GPU-hour).")
    bullet(doc, "Budget: HKD 2,000 per student; roughly HKD 500–560 already consumed by the current 60-pair run.")
    bullet(doc, "Python ≥ 3.10; torch ≥ 2.4 with cu121; flash-attn matching the torch/CUDA build. Record exact versions.")
    bullet(doc, "Disk: reserve at least 200 GB for Wan2.2 weights, T5/VAE assets, 60 MP4 outputs and temporary frames.")
    bullet(doc, "If you have fewer than 8×80 GB, or a different GPU generation (A100/H100/4090), tell me before running: the launcher and the wall-clock cost will differ.")

    heading(doc, "3. Model and inference settings")
    table(
        doc,
        [
            ["Setting", "Value / instruction"],
            ["Repository", "https://github.com/HKUST-C4G/EchoStyle — exact commit is pinned in the shard manifest (fill before start)"],
            ["Checkpoint", "EchoStyle LoRA / full checkpoint pinned in the shard manifest (fill before start)"],
            ["Mode", "Standard 50-step mode; confirm the exact sample_steps in the shard manifest. Lightning (10-step) outputs are NOT comparable with standard outputs."],
            ["Resolution", "1280×720 (EchoStyle default --size 1280*720)"],
            ["Frames", "81 frames per clip"],
            ["Seeds", "experiment seed 2026; method seed 42"],
            ["Guidance / shift", "EchoStyle defaults; record the exact values you use"],
            ["Batch", "1 clip per forward (per-clip timing); do not change to compare runtime"],
            ["Long video", "Sliding-window long-video inference is not used; clips average 5.06 s"],
        ],
        widths=[4.2, 12.6],
        font_size=9.5,
    )
    para(
        doc,
        "Before running, fill the commit, checkpoint, guidance and sample_steps values in the shard manifest and send them back. "
        "A standard/lightning mismatch invalidates every comparison.",
        size=9.5,
        color=GREY,
    )

    heading(doc, "4. Dataset and manifest")
    para(doc, "Source: https://huggingface.co/datasets/HiDream-ai/ReCo-Bench — custom subset 'subset5' (first five stylization videos, all 12 styles).")
    para(doc, "Manifest: evaluation_run/reco_12style_5sample/inputs/manifest.json (schema 1.0). Each case has id, content_id, style_id, source_video, style_prompt and an outputs map.")
    para(doc, "Case ID format: <content_id>__<style_id>, e.g. 3129424-uhd_3840_2160_24fps__Ghibli. Use the ID verbatim; do not add suffixes.")
    para(doc, "Source videos (5):", bold=True)
    for content in content_ids:
        bullet(doc, content)
    para(doc, "Styles (12):", bold=True)
    bullet(doc, ", ".join(styles))
    para(
        doc,
        "Style condition is text-only: the manifest carries a Chinese style_prompt per case and no style_image. "
        "Therefore the LAB palette metrics are intentionally skipped; this is not a failure.",
        size=9.5,
        color=GREY,
    )

    heading(doc, "5. Output contract")
    para(doc, "Write one MP4 per case to:")
    code(doc, "outputs/echostyle/<case_id>_gen.mp4")
    bullet(doc, "Keep the source frame rate and duration; H.264, yuv420p, no re-timing, no cropping.")
    bullet(doc, "Do not rename, transcode or concatenate outputs; the evaluation matches by filename.")
    bullet(doc, "Return the MP4s plus one JSON record per clip with the schema below.")
    code(
        doc,
        '{\n  "case_id": "3129424-uhd_3840_2160_24fps__Ghibli",\n'
        '  "runtime_s": 266.1,\n  "peak_gpu_gb": 75.8,\n  "gpu": "8x H800 80GB",\n'
        '  "echo_style_commit": "<fill>",\n  "checkpoint": "<fill>",\n'
        '  "mode": "standard-50",\n  "resolution": "1280x720",\n  "frames": 81,\n  "seed": 2026\n}',
    )

    heading(doc, "6. Cost and budget")
    table(
        doc,
        [
            ["Scope", "Wall-clock", "GPU-minutes (8 GPUs)", "Est. cost (HKD)"],
            ["1 clip", "266.1 s", "35.5", "7.1"],
            ["30 pairs", "≈ 2.2 h", "1,064", "213"],
            ["36 pairs", "≈ 2.7 h", "1,277", "255"],
            ["24 pairs", "≈ 1.8 h", "851", "170"],
            ["60 pairs", "≈ 4.4 h", "2,130", "426"],
        ],
        widths=[3.2, 3.4, 5.0, 4.4],
        font_size=9.5,
    )
    para(
        doc,
        "Costs use my 8×H800 measurement and HKD 0.20/GPU-min. Your wall-clock will differ on other hardware; "
        "report it separately rather than rescaling mine.",
        size=9,
        color=GREY,
    )

    heading(doc, "7. Evaluation pipeline — who runs what")
    table(
        doc,
        [
            ["Step", "Owner", "Notes"],
            ["EchoStyle inference", "Friend + me (split)", "MP4s + runtime/peak-memory JSON"],
            ["Diagnostics (SSIM/PSNR/flicker/warp/flow)", "Me", "OpenCV Farneback; CPU, deterministic"],
            ["VBench custom_input (7 dims)", "Me", "Same VBench version for every method"],
            ["CSD-S / CSD-C", "Me", "yuxi-liu-wired/CSD, CLIP ViT-L/14, --max-frames 32"],
            ["VLM review", "Me", "Qwen3-VL-Plus, single-blind contact sheets, 1–5 rubric"],
            ["Merge + report + slides", "Me", "No CUDA needed"],
        ],
        widths=[6.0, 3.4, 6.8],
        font_size=9.5,
    )
    para(doc, "Metrics reported: SSIM, PSNR, CSD-S, CSD-C, detrended luminance flicker, warp RMSE Δ1/Δ5, flow EPE, flow correlation, VBench subject/background/temporal flicker/motion smoothness/aesthetic/imaging/dynamic degree, runtime and peak GPU memory, plus the five VLM dimensions (1–5).")
    para(doc, "LAB palette W1 and chroma W1 are skipped because the style condition is text-only (no style image).", size=9, color=GREY)

    heading(doc, "8. Sharding options")
    para(doc, "Option A — split by source video (recommended if your node is comparable):", bold=True)
    table(
        doc,
        [
            ["Owner", "Source videos", "Pairs"],
            ["Me", "3129424-uhd_3840_2160_24fps; 3201691-hd_1920_1080_25fps; 3873059-hd_1920_1080_25fps", "36"],
            ["You", "3195531-uhd_3840_2160_25fps_resampled; 3254006-uhd_3840_2160_25fps", "24"],
        ],
        widths=[2.6, 11.4, 2.2],
        font_size=9.5,
    )
    para(doc, "Option B — split by style (exactly 30/30):", bold=True)
    table(
        doc,
        [
            ["Owner", "Styles", "Pairs"],
            ["Me", "Paper_Cutting, Simpsons, Sketch, Ukiyo-e, Van_Gogh, Watercolor", "30"],
            ["You", "3D_Chibi, American_Cartoon, Ghibli, Irasutoya, Jojo, Monet", "30"],
        ],
        widths=[2.6, 11.4, 2.2],
        font_size=9.5,
    )
    bullet(doc, "No overlap: each case_id is generated exactly once.")
    bullet(doc, "I will send a shard manifest with only your case IDs, plus the exact commit/checkpoint and a runtime logger.")
    bullet(doc, "Merge is by case_id; filenames and IDs must match the manifest exactly.")

    heading(doc, "9. MUST MATCH vs MAY DIFFER")
    table(
        doc,
        [
            ["MUST MATCH", "MAY DIFFER (report it)"],
            ["EchoStyle commit and checkpoint", "GPU model and count"],
            ["Standard vs lightning, sample_steps", "Batch size (but report per-clip time)"],
            ["Guidance / shift / seed", "Wall-clock runtime"],
            ["Resolution 1280×720, 81 frames", "CUDA minor version (same major stack)"],
            ["Source files and style prompts", "Hostname / filesystem layout"],
            ["Output naming and case IDs", "Number of workers"],
            ["Runtime definition (per clip)", "—"],
        ],
        widths=[8.4, 8.4],
        font_size=9.5,
    )

    heading(doc, "10. Return package checklist")
    bullet(doc, "MP4s under outputs/echostyle/ with the exact <case_id>_gen.mp4 names.")
    bullet(doc, "runtime.jsonl or runtime.json: one record per clip with the schema in Section 5.")
    bullet(doc, "A short environment note: GPU model/count, torch, CUDA, flash-attn, EchoStyle commit, checkpoint, mode/steps, guidance.")
    bullet(doc, "sha256sum.txt for the MP4s (optional but useful for transfer integrity).")
    bullet(doc, "Confirmation of which shard option you take.")

    heading(doc, "11. Open questions for you")
    bullet(doc, "GPU model and count on your side?")
    bullet(doc, "EchoStyle commit + checkpoint you will use?")
    bullet(doc, "Standard 50-step or lightning 10-step? Exact sample_steps and guidance?")
    bullet(doc, "Do you have enough local disk for 60 MP4s plus Wan2.2 weights?")
    bullet(doc, "Option A (36/24 by video) or Option B (30/30 by style)?")

    heading(doc, "12. VBench model configuration")
    para(
        doc,
        "VBench is run in custom_input mode on the generated MP4s (no prompt suite). "
        "All seven dimensions must use the same VBench version and the same model weights on both sides; "
        "a version/weight mismatch changes the scores.",
    )
    table(
        doc,
        [
            ["VBench dimension", "Model / method", "How it is used", "Score"],
            ["subject_consistency", "DINO ViT-S/16", "Per-frame 224×224 features; adjacent-frame cosine similarity", "0–1 ↑"],
            ["background_consistency", "CLIP ViT-B/32", "Per-frame 224×224 features; adjacent-frame cosine similarity", "0–1 ↑"],
            ["temporal_flickering", "No neural model", "Mean absolute pixel difference between adjacent frames", "0–1 ↑"],
            ["motion_smoothness", "AMT frame interpolation", "Interpolate held-out frame from neighbours; interpolation error", "0–1 ↑"],
            ["dynamic_degree", "RAFT optical flow", "Mean flow magnitude above threshold; fraction of dynamic clips", "0–1 ↑"],
            ["aesthetic_quality", "LAION Aesthetic Predictor (CLIP ViT-L/14 + MLP)", "Per-frame aesthetic score, averaged over frames", "0–1 ↑"],
            ["imaging_quality", "MUSIQ (no-reference IQA)", "Per-frame MUSIQ score, averaged and normalized", "0–1 (MUSIQ/100) ↑"],
        ],
        widths=[3.4, 5.0, 6.4, 2.6],
        font_size=8.5,
    )
    table(
        doc,
        [
            ["Pinned item", "Value (fill before running)"],
            ["VBench version / commit", "<fill — must be identical on both sides>"],
            ["VBench mode", "custom_input; 7 dimensions listed above"],
            ["DINO weights", "dino_vits16"],
            ["CLIP weights", "ViT-B/32 (image encoder)"],
            ["AMT checkpoint", "<fill — VBench default checkpoint>"],
            ["RAFT checkpoint", "<fill — VBench default checkpoint>"],
            ["MUSIQ model", "<fill — pyiqa model name/version>"],
            ["LAION aesthetic checkpoint", "<fill — predictor version>"],
        ],
        widths=[6.0, 12.0],
        font_size=8.5,
    )
    para(
        doc,
        "Current gap: our vbench.json stores scores only and does not record the VBench version or weight files. "
        "Pin them in the shard manifest before you start; do not upgrade VBench between the two shards.",
        size=9,
        color=GREY,
    )

    heading(doc, "Appendix A — All 60 case IDs")
    rows = [["#", "Case ID"]]
    for index, case in enumerate(cases, start=1):
        rows.append([str(index), case["id"]])
    table(doc, rows, widths=[1.2, 15.0], font_size=8.5)

    OUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_DOCX)
    print("wrote", OUT_DOCX, "cases", len(cases))


if __name__ == "__main__":
    main()
