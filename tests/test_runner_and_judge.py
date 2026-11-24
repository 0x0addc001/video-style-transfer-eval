"""Resume/timing wrapper and VLM judge prompt/parse tests."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from resume_inference import expected_output, split_pending  # noqa: E402
from vlm_judge import build_prompt, parse_scores  # noqa: E402


class ResumeInferenceTest(unittest.TestCase):
    def test_expected_output_uses_stem(self) -> None:
        output = expected_output(
            {"src_video_path": "assets/videos/01.mp4"},
            Path("/tmp/out"),
            "{stem}_gen.mp4",
        )
        self.assertEqual(output, Path("/tmp/out/01_gen.mp4"))

    def test_split_pending_skips_existing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "01_gen.mp4").write_bytes(b"")
            items = [
                {"src_video_path": "videos/01.mp4"},
                {"src_video_path": "videos/02.mp4"},
            ]
            pending, done = split_pending(items, directory, "{stem}_gen.mp4")
            self.assertEqual([item["src_video_path"] for item in done], ["videos/01.mp4"])
            self.assertEqual([item["src_video_path"] for item in pending], ["videos/02.mp4"])

    def test_cli_resumes_and_writes_timings(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "out").mkdir()
            (directory / "out" / "01_gen.mp4").write_bytes(b"")
            input_path = directory / "input.json"
            input_path.write_text(
                json.dumps(
                    [
                        {"src_video_path": "videos/01.mp4"},
                        {"src_video_path": "videos/02.mp4"},
                    ]
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "resume_inference.py"),
                    "--input",
                    str(input_path),
                    "--output-dir",
                    str(directory / "out"),
                    "--command",
                    "true",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            timings = json.loads(
                (directory / "out" / "timings.json").read_text(encoding="utf-8")
            )
            self.assertEqual(timings["skipped_as_done"], 1)
            self.assertEqual(timings["pending"], 1)
            self.assertFalse((directory / "out" / "pending.json").exists())


class VlmJudgeTest(unittest.TestCase):
    def test_prompt_lists_labels_and_json_contract(self) -> None:
        prompt = build_prompt("case_01", ["M1", "M2"])
        self.assertIn("M1, M2", prompt)
        self.assertIn("style_adherence", prompt)
        self.assertIn("Return JSON only", prompt)

    def test_parse_scores_handles_fences_and_clamps(self) -> None:
        raw = (
            "```json\n"
            '{"scores": [{"method_blind_id": "M1", "style_adherence": 9, '
            '"content_preservation": 3, "temporal_stability": 3, '
            '"artifact_control": 3, "overall_visual_quality": 3, '
            '"confidence": "high", "failure_tags": ["flicker", "bogus"], '
            '"evidence": "e", "comments": "c"}]}\n'
            "```"
        )
        scores = parse_scores(raw, "case_01", ["M1"])
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0]["style_adherence"], 5)
        self.assertEqual(scores[0]["failure_tags"], ["flicker"])
        self.assertEqual(scores[0]["case_id"], "case_01")

    def test_parse_scores_ignores_unknown_labels(self) -> None:
        raw = json.dumps(
            {"scores": [{"method_blind_id": "M9", "style_adherence": 4}]}
        )
        self.assertEqual(parse_scores(raw, "case_01", ["M1"]), [])


if __name__ == "__main__":
    unittest.main()
