---
name: video-style-transfer-eval
description: Evaluate video style transfer outputs with reproducible frame and motion metrics, blinded visual-language-model review, and an evidence-backed report. Use for model comparison, ablations, failure analysis, or deciding whether a VST result is ready to report; do not use it to claim stylistic success from pixel similarity alone.
---

# Video Style Transfer Evaluation

Evaluate a source video, one or more style references, and one or more generated videos as a paired experiment. Preserve style, content, motion, and temporal evidence as separate measurements. Report missing or non-comparable evidence explicitly.

## Read First

Before choosing metrics or interpreting scores, read [references/evaluation-protocol.md](references/evaluation-protocol.md). For visual scoring and prompt construction, read [references/vlm-rubric.md](references/vlm-rubric.md). Before producing the deliverable, read [references/report-spec.md](references/report-spec.md).

## Workflow

1. Build a manifest from [assets/manifest.example.json](assets/manifest.example.json). Make method comparisons paired on the same source clip and style image. Keep development, validation, and test splits distinct.
2. Record reproducibility fields before running inference: checkpoint or commit, seed, resolution, frame rate, clip duration, sampling schedule, hardware, and whether the style reference was also used during training.
3. Run the diagnostic metric pass:

   ```bash
   python video-style-transfer-eval/scripts/evaluate.py \
     --manifest manifest.json \
     --output-dir evaluation_run \
     --blind
   ```

   This computes readability, PSNR, SSIM, LAB palette distance, source-flow warping error, flow endpoint error, flow correlation, and luminance flicker. These are reproducible diagnostics, not substitutes for LPIPS, CLIP-I/CLIP-F, FID, or ArtFID.
4. Inspect `evaluation_run/metrics.json`; resolve duration, frame-count, aspect-ratio, or decode warnings before interpreting results. Omit failed cases rather than silently averaging them. If LPIPS, CLIP-I/F, FID, ArtFID, tLP, or CLIP-CONS are computed with a fixed external implementation, merge them through `scripts/merge_metrics.py`; record that implementation in the evidence file and report.
5. Review the generated contact sheets with a vision-language model or a human reviewer. Use only the blinded labels in `review_packet/`; do not open `blind_map.json` until scoring is complete. Save one completed JSON file per reviewer using [references/vlm-rubric.md](references/vlm-rubric.md).
6. Validate all reviews:

   ```bash
   python video-style-transfer-eval/scripts/validate_review.py \
     --review reviews/*.json \
     --blind-map evaluation_run/review_packet/blind_map.json
   ```
7. Render the fixed report:

   ```bash
   python video-style-transfer-eval/scripts/render_report.py \
     --metrics evaluation_run/metrics.json \
     --review evaluation_run/review_packet/validated_reviews.json \
     --output-dir evaluation_report \
     --language both \
     --primary METHOD_ID \
     --baseline BASELINE_ID
   ```

   Replace `METHOD_ID` and `BASELINE_ID` with manifest IDs. Omit those flags only when there is no meaningful primary comparison. `--language both` generates English and Chinese Markdown, HTML, PDF, and LaTeX reports. Use `--title-zh` and `--claim-zh` when the Chinese report needs project-specific wording. Chinese PDFs auto-detect common CJK fonts; pass `--cjk-font PATH` or set `VST_EVAL_CJK_FONT` in minimal environments.

8. Inspect both language versions of the Markdown, HTML, PDF, and LaTeX. Confirm the metric-definition section states each formula, motivation, availability, and reporting caveat. Check the evidence-completeness table before making a comparative or paper-ready claim. Include representative success and failure examples, with timestamps and the corresponding source/style pair.

## Evidence Rules

- Treat lower warping error as better temporal stability and lower flow EPE as better motion agreement. SSIM and PSNR are content diagnostics; LPIPS and CLIP-F are preferable perceptual and semantic content evidence when available.
- Do not interpret a high style-palette score as proof of texture transfer. The diagnostic palette metric can reward global recoloring while missing brushwork, texture sticking, or semantic distortion.
- Compare methods at similar achieved style strength when testing preservation. A method that stylizes weakly can otherwise appear to preserve content and motion trivially.
- Never invent CLIP, LPIPS, FID, ArtFID, RAFT, or VLM values. Label Fast-Farneback values as proxies; use the same implementation for all methods if making a quantitative comparison.
- If FID/ArtFID is required, use a style distribution with enough independent references and record the feature extractor, image count, resolution, and preprocessing. Do not compute a paper-style FID against a single style image and call it comparable.
- VLM scores are perceptual evidence, not ground truth. Blind method labels, report model/version, sample frames, and preserve evidence or failure tags for every non-default score.
- Report uncertainty and per-case results. Do not collapse style, preservation, motion, temporal stability, and cost into an unexplained single score.

## Output Contract

The completed run has:

```text
evaluation_run/
  metrics.json
  contact_sheets/
  review_packet/
    blind_map.json
    packet.json
    completed_review_template.json
evaluation_report/
  report_en.md
  report_en.html
  report_en.pdf
  report_en.tex
  report_zh.md
  report_zh.html
  report_zh.pdf
  report_zh.tex
  assets/
```

Single-language mode writes `report.md`, `report.html`, `report.pdf`, and `report.tex`. The report uses publication-style tables with mean and dispersion, best and second-best means, direction-adjusted paired effects, evidence-gated analysis, and copyable `booktabs` LaTeX tables. The report sections, evidence gates, bilingual parity, and claim language are fixed by [references/report-spec.md](references/report-spec.md).
