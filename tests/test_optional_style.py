"""Text-driven methods can run the diagnostics without a style image."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate.py"
DEMO = ROOT / "examples" / "sample_report" / "demo_run"


class OptionalStyleImageTest(unittest.TestCase):
    def test_manifest_without_style_image_skips_palette_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest = {
                "schema_version": "1.0",
                "experiment": {
                    "title": "text-only smoke",
                    "split": "smoke",
                    "frame_limit": 6,
                    "max_side": 160,
                    "temporal_offsets": [1],
                },
                "methods": [{"id": "echostyle", "label": "EchoStyle"}],
                "cases": [
                    {
                        "id": "case_01",
                        "content_id": "content_01",
                        "style_id": "ghibli",
                        "split": "smoke",
                        "source_video": str(
                            (DEMO / "data/source/demo_case_01.mp4").resolve()
                        ),
                        "outputs": {
                            "echostyle": {
                                "video": str(
                                    (DEMO / "data/outputs/balanced/demo_case_01.mp4").resolve()
                                ),
                                "runtime_s": 12.0,
                            }
                        },
                    }
                ],
            }
            manifest_path = directory / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            run_dir = directory / "run"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--manifest",
                    str(manifest_path),
                    "--output-dir",
                    str(run_dir),
                    "--blind",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            metrics = json.loads(
                (run_dir / "metrics.json").read_text(encoding="utf-8")
            )
            case = metrics["cases"][0]
            method_metrics = case["methods"]["echostyle"]["metrics"]
            self.assertIsNone(case.get("style_image"))
            self.assertNotIn("lab_palette_w1", method_metrics)
            self.assertNotIn("lab_ab_palette_w1", method_metrics)
            self.assertIn("ssim", method_metrics)
            self.assertTrue(
                any("style_image" in warning for warning in case["warnings"])
            )


if __name__ == "__main__":
    unittest.main()
