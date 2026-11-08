# Video Style Transfer Evaluation

**Languages:** [English](README.md) | [简体中文](README.zh-CN.md)

A Codex skill for evaluating video style transfer outputs with paired
style-content-motion diagnostics, blinded visual-language-model review, and
evidence-gated reports.

The tool keeps four questions separate:

1. Does the output adopt the reference style?
2. Does it preserve source content and structure?
3. Does it preserve motion and remain stable over time?
4. What runtime and memory cost does it require?

It produces separate English and Chinese PDF/HTML/Markdown/XeLaTeX reports from
the same machine-readable evidence.

The bundled example under `examples/sample_report` is synthetic. It demonstrates
the evaluation workflow and is not a benchmark of any model.

## Features

- Paired source/style/output manifests.
- Deterministic diagnostics: SSIM, PSNR, LAB palette distance, Farneback flow
  EPE, source-flow warping error, flow correlation, and luminance flicker.
- Blinded contact sheets with per-case randomized method labels.
- A 1-5 VLM/human rubric for style, content, temporal stability, artifacts, and
  overall quality.
- A strict review validator and evidence tags.
- Merge support for fixed external metrics such as LPIPS, CLIP-I/F, FID,
  ArtFID, tLP, and CLIP-CONS.
- English and Chinese Markdown, standalone HTML, PDF, and XeLaTeX reports.
- Per-case evidence, uncertainty caveats, failure analysis, and claim-status
  gates.

## Install

Install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Install the skill for Codex by copying this directory into
`$CODEX_HOME/skills` or `~/.codex/skills`:

```powershell
Copy-Item -Recurse . "$env:USERPROFILE\.codex\skills\video-style-transfer-eval"
```

Chinese PDF rendering requires a CJK font with TrueType outlines. The script
auto-detects common Windows, Linux, and macOS fonts. On Linux, install
`fonts-wqy-zenhei` or pass a compatible font:

```bash
python scripts/render_report.py ... \
  --cjk-font /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc
```

## Quick Start

Create a manifest from [assets/manifest.example.json](assets/manifest.example.json),
then run:

```bash
python scripts/evaluate.py \
  --manifest manifest.json \
  --output-dir evaluation_run \
  --blind
```

Review the generated contact sheets using [references/vlm-rubric.md](references/vlm-rubric.md),
then validate the review:

```bash
python scripts/validate_review.py \
  --review reviews/*.json \
  --blind-map evaluation_run/review_packet/blind_map.json
```

Render both languages:

```bash
python scripts/render_report.py \
  --metrics evaluation_run/metrics.json \
  --review evaluation_run/review_packet/validated_reviews.json \
  --output-dir evaluation_report \
  --language both \
  --primary METHOD_ID \
  --baseline BASELINE_ID
```

The output contains:

```text
evaluation_report/
  report_en.pdf
  report_en.html
  report_en.md
  report_en.tex
  report_zh.pdf
  report_zh.html
  report_zh.md
  report_zh.tex
  assets/
```

Use `--language en` or `--language zh` when only one report is needed.
The LaTeX files are standalone XeLaTeX documents with `booktabs` tables,
publication-style captions, best/second-best marking, paired effect sizes,
data-driven discussion, and per-case evidence for direct adaptation into a CVPR
or other computer-vision manuscript.

## Metric Scope

Farneback flow and LAB palette distance are deterministic diagnostic proxies.
They are not substitutes for RAFT, LPIPS, CLIP-I/F, FID, or ArtFID. Use
`scripts/merge_metrics.py` with a fixed external implementation and report the
implementation version and preprocessing.

See:

- [Evaluation protocol](references/evaluation-protocol.md)
- [VLM rubric](references/vlm-rubric.md)
- [Report specification](references/report-spec.md)

## Testing

Run the smoke tests:

```bash
python -m unittest discover -s tests -v
```

## Repository Layout

```text
SKILL.md
agents/
assets/
references/
scripts/
tests/
examples/sample_report/
```

The skill follows Codex's progressive-disclosure convention: `SKILL.md` contains
the operating workflow, while detailed protocols and schemas live in
`references/`.

## License

MIT. See [LICENSE](LICENSE).
