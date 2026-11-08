# Video Style Transfer Evaluation

A Codex skill for evaluating video style transfer outputs with paired
style-content-motion diagnostics, blinded visual-language-model review, and
evidence-gated reports.

The tool keeps four questions separate:

1. Does the output adopt the reference style?
2. Does it preserve source content and structure?
3. Does it preserve motion and remain stable over time?
4. What runtime and memory cost does it require?

It produces separate English and Chinese PDF/HTML/Markdown reports from the same
machine-readable evidence.

The bundled example under `examples/sample_report` is synthetic. It demonstrates
the evaluation workflow and is not a benchmark of EchoStyle, UniVST, or another
production model.

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
- English and Chinese Markdown, standalone HTML, and PDF reports.
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

Chinese PDF rendering requires a CJK font. The script auto-detects common
Windows, Linux, and macOS fonts. On Linux, install `fonts-noto-cjk` or pass:

```bash
python scripts/render_report.py ... \
  --cjk-font /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
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
  report_zh.pdf
  report_zh.html
  report_zh.md
  assets/
```

Use `--language en` or `--language zh` when only one report is needed.

## Metric Scope

Farneback flow and LAB palette distance are deterministic diagnostic proxies.
They are not substitutes for RAFT, LPIPS, CLIP-I/F, FID, or ArtFID. Use
`scripts/merge_metrics.py` with a fixed external implementation and report the
implementation version and preprocessing.

See:

- [Evaluation protocol](references/evaluation-protocol.md)
- [VLM rubric](references/vlm-rubric.md)
- [Report specification](references/report-spec.md)

## 中文简介

本项目提供一个用于视频风格迁移评估的 Codex 技能，分别评估风格迁移、内容保持、
运动一致性与时序稳定性，并支持盲评 VLM 审查。

脚本会从同一份指标和审查数据生成英文、中文两套 Markdown、HTML 和 PDF 报告。
合成示例只用于验证评估流程，不代表 EchoStyle、UniVST 或实际模型性能。

运行测试：

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
