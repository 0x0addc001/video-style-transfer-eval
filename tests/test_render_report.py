from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_report.py"


class BilingualRenderTest(unittest.TestCase):
    def test_bilingual_outputs_are_created_and_localized(self) -> None:
        fixture = {
            "schema_version": "1.0",
            "manifest_sha256": "test",
            "experiment": {
                "split": "test",
                "frame_limit": 8,
                "max_side": 320,
                "temporal_offsets": [1],
                "blind": True,
                "flow_implementation": "OpenCV Farneback (diagnostic proxy)",
            },
            "methods": [
                {"id": "ours", "label": "Ours", "label_zh": "本文方法"},
                {"id": "baseline", "label": "Baseline", "label_zh": "基线方法"},
            ],
            "metric_info": {
                "ssim": {
                    "label": "SSIM",
                    "dimension": "content",
                    "higher_is_better": True,
                    "unit": "",
                }
            },
            "cases": [
                {
                    "id": "case_001",
                    "content_id": "content_001",
                    "style_id": "style_001",
                    "split": "test",
                    "warnings": [],
                    "methods": {
                        "ours": {
                            "valid": True,
                            "metrics": {"ssim": 0.91, "runtime_s": 1.0},
                        },
                        "baseline": {
                            "valid": True,
                            "metrics": {"ssim": 0.84, "runtime_s": 2.0},
                        },
                    },
                }
            ],
            "aggregates": {
                "ours": {
                    "ssim": {
                        "n": 1,
                        "mean": 0.91,
                        "std": 0.0,
                        "median": 0.91,
                        "min": 0.91,
                        "max": 0.91,
                        "ci95_mean": None,
                    }
                },
                "baseline": {
                    "ssim": {
                        "n": 1,
                        "mean": 0.84,
                        "std": 0.0,
                        "median": 0.84,
                        "min": 0.84,
                        "max": 0.84,
                        "ci95_mean": None,
                    }
                },
            },
            "pairwise": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metrics_path = root / "metrics.json"
            metrics_path.write_text(json.dumps(fixture), encoding="utf-8")
            output_dir = root / "report"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--metrics",
                    str(metrics_path),
                    "--output-dir",
                    str(output_dir),
                    "--language",
                    "both",
                    "--primary",
                    "ours",
                    "--baseline",
                    "baseline",
                    "--status",
                    "Exploratory",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for suffix in ("md", "html", "pdf", "tex"):
                for lang in ("en", "zh"):
                    path = output_dir / f"report_{lang}.{suffix}"
                    self.assertTrue(path.is_file(), path)
                    self.assertGreater(path.stat().st_size, 100, path)
            english_html = (output_dir / "report_en.html").read_text(encoding="utf-8")
            chinese_html = (output_dir / "report_zh.html").read_text(encoding="utf-8")
            self.assertIn("Quantitative results", english_html)
            self.assertIn("Analysis and discussion", english_html)
            self.assertIn("定量结果", chinese_html)
            self.assertIn("本文方法", chinese_html)
            english_tex = (output_dir / "report_en.tex").read_text(encoding="utf-8")
            chinese_tex = (output_dir / "report_zh.tex").read_text(encoding="utf-8")
            self.assertIn(r"\usepackage{booktabs}", english_tex)
            self.assertIn(r"\begin{table}[H]", english_tex)
            self.assertIn(r"\documentclass[UTF8,10pt]{ctexart}", chinese_tex)


if __name__ == "__main__":
    unittest.main()
