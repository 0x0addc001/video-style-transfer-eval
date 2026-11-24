#!/usr/bin/env python3
"""Regenerate the sample report and the published homepage from one run.

The bilingual homepage in ``docs/index.html`` is merged from the two sample
report HTML files, so both must come from the same generation. This script runs
the renderer twice (en/zh) and then rebuilds the homepage, keeping the report
IDs in sync.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "sample_report"
REPORT_DIR = SAMPLE / "evaluation_report"

ARGS = [
    "--metrics", str(SAMPLE / "demo_evaluation" / "metrics.json"),
    "--review", str(SAMPLE / "demo_evaluation" / "review_packet" / "validated_reviews.json"),
    "--output-dir", str(REPORT_DIR),
    "--language", "both",
    "--title", "Video Style Transfer Evaluation Report (Sample)",
    "--title-zh", "视频风格迁移评估报告（样例）",
    "--primary", "balanced",
    "--baseline", "flicker",
    "--status", "Exploratory",
    "--note",
    "Synthetic demo clips and stand-in CSD/VBench values; the numbers illustrate the workflow, not model performance.",
    "--note-zh",
    "示例为合成片段与 CSD/VBench 占位数值，仅用于演示评估流程，不代表模型性能。",
]


def run(command: list[str]) -> None:
    print("$", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    run([sys.executable, "scripts/render_report.py", *ARGS])
    run(
        [
            sys.executable,
            "scripts/build_homepage.py",
            "--en", str(REPORT_DIR / "report_en.html"),
            "--zh", str(REPORT_DIR / "report_zh.html"),
            "--output", str(ROOT / "docs" / "index.html"),
            "--assets", str(REPORT_DIR / "assets"),
            "--default-language", "zh",
        ]
    )
    print("Sample report and homepage are in sync.")


if __name__ == "__main__":
    main()
