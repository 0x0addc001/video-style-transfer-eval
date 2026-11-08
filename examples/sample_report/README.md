# Video Style Transfer Evaluation Sample

This sample demonstrates the full `video-style-transfer-eval` workflow:

1. paired synthetic source/style/output manifest;
2. source-flow temporal diagnostics;
3. blinded visual review packet;
4. validated VLM scores;
5. Markdown, HTML, and PDF report generation.

The clips and methods are synthetic and deliberately contain different style,
content, and temporal trade-offs. They are not measurements of EchoStyle, UniVST,
or the user's proposed method.

Open the polished samples:

- [English PDF](evaluation_report/report_en.pdf)
- [Chinese PDF](evaluation_report/report_zh.pdf)
- [English HTML](evaluation_report/report_en.html)
- [Chinese HTML](evaluation_report/report_zh.html)
- [English LaTeX](evaluation_report/report_en.tex)
- [Chinese LaTeX](evaluation_report/report_zh.tex)

The LaTeX sources are standalone XeLaTeX documents and were compile-checked
with Tectonic 0.17.0.

The machine-readable evidence is in
[demo_evaluation/metrics.json](demo_evaluation/metrics.json), and the review export is
[demo_evaluation/review_packet/validated_reviews.json](demo_evaluation/review_packet/validated_reviews.json).

To rebuild on Windows:

```powershell
python examples/sample_report/build_demo.py
python scripts/evaluate.py `
  --manifest examples/sample_report/demo_run/manifest.json `
  --output-dir examples/sample_report/demo_evaluation `
  --blind
python scripts/validate_review.py `
  --review examples/sample_report/demo_review/codex_sample_review.json `
  --blind-map examples/sample_report/demo_evaluation/review_packet/blind_map.json
python scripts/render_report.py `
  --metrics examples/sample_report/demo_evaluation/metrics.json `
  --review examples/sample_report/demo_evaluation/review_packet/validated_reviews.json `
  --output-dir examples/sample_report/evaluation_report `
  --language both `
  --title "Video Style Transfer Evaluation - Synthetic Workflow Demonstration" `
  --title-zh "视频风格迁移评估 - 合成流程演示" `
  --claim "Demonstrate a reproducible style-content-motion evaluation workflow without presenting synthetic clips as model benchmark evidence." `
  --claim-zh "演示可复现的风格、内容与运动评估流程，并明确合成片段不能作为模型基准证据。" `
  --primary balanced `
  --baseline flicker `
  --status Exploratory
```
