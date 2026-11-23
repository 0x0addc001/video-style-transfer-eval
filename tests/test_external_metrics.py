"""Tests for the CSD and VBench external-metric adapters."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from csd_consistency import cosine_first_frame, sequence_metrics  # noqa: E402
from evidence_io import (  # noqa: E402
    build_video_lookup,
    match_video,
    select_frame_indices,
)
from metric_registry import EXTERNAL_METRIC_INFO  # noqa: E402


def write_manifest(directory: Path, methods: list[str], case_ids: list[str]) -> Path:
    cases = []
    for case_id in case_ids:
        outputs = {
            method: {"video": f"outputs/{method}/{case_id}.mp4"}
            for method in methods
        }
        cases.append(
            {
                "id": case_id,
                "content_id": f"content_{case_id}",
                "style_id": f"style_{case_id}",
                "split": "test",
                "outputs": outputs,
            }
        )
    payload = {
        "schema_version": "1.0",
        "experiment": {"split": "test"},
        "methods": [{"id": method, "label": method} for method in methods],
        "cases": cases,
    }
    path = directory / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    for case in cases:
        for output in case["outputs"].values():
            video = directory / output["video"]
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"")
    return path


class FrameSamplingTest(unittest.TestCase):
    def test_evenly_spaced_indices_include_first_frame(self) -> None:
        self.assertEqual(select_frame_indices(10, 4), [0, 3, 6, 9])

    def test_short_videos_keep_every_frame(self) -> None:
        self.assertEqual(select_frame_indices(3, 5), [0, 1, 2])

    def test_single_frame_budget(self) -> None:
        self.assertEqual(select_frame_indices(9, 1), [0])

    def test_empty_video(self) -> None:
        self.assertEqual(select_frame_indices(0, 8), [])


class CSDMathTest(unittest.TestCase):
    def test_cosine_against_first_frame(self) -> None:
        embeddings = np.array(
            [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
            dtype=np.float64,
        )
        self.assertAlmostEqual(cosine_first_frame(embeddings), 0.5)

    def test_single_frame_has_no_consistency(self) -> None:
        self.assertIsNone(cosine_first_frame(np.ones((1, 4))))

    def test_sequence_metrics_are_rounded(self) -> None:
        style = np.array([[1.0, 0.0], [0.6, 0.8]], dtype=np.float64)
        content = np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float64)
        metrics = sequence_metrics(style, content)
        self.assertEqual(set(metrics), {"csd_s", "csd_c"})
        self.assertAlmostEqual(metrics["csd_s"], 0.6)
        self.assertAlmostEqual(metrics["csd_c"], 1.0)
        self.assertEqual(metrics["csd_s"], round(metrics["csd_s"], 6))

    def test_degenerate_embeddings_are_skipped(self) -> None:
        zeros = np.zeros((2, 3))
        self.assertEqual(sequence_metrics(zeros, zeros), {})


class ManifestLookupTest(unittest.TestCase):
    def test_basename_matching_is_used_when_unique(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest_path = write_manifest(directory, ["ours"], ["case_001"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            lookup = build_video_lookup(manifest, directory)
            match = match_video(lookup, "some/other/prefix/case_001.mp4")
            self.assertEqual(match, ("case_001", "ours"))

    def test_ambiguous_basenames_are_not_guessed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest_path = write_manifest(
                directory, ["ours", "baseline"], ["case_001"]
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            lookup = build_video_lookup(manifest, directory)
            self.assertIsNone(match_video(lookup, "case_001.mp4"))

    def test_exact_path_wins_over_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest_path = write_manifest(
                directory, ["ours", "baseline"], ["case_001"]
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            lookup = build_video_lookup(manifest, directory)
            exact = str((directory / "outputs/baseline/case_001.mp4").resolve())
            self.assertEqual(match_video(lookup, exact), ("case_001", "baseline"))


class VBenchImportTest(unittest.TestCase):
    def run_adapter(self, arguments: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "vbench_import.py"), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_mixed_result_shapes_are_imported(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest = write_manifest(directory, ["ours", "baseline"], ["case_001"])
            results = directory / "vbench"
            results.mkdir()
            # Shape A: plain list of per-video entries.
            (results / "run_motion_eval_results.json").write_text(
                json.dumps(
                    {
                        "motion_smoothness": [
                            {
                                "video_path": str(
                                    directory / "outputs/ours/case_001.mp4"
                                ),
                                "video_results": 0.91,
                            },
                            {
                                "video_path": "outputs/baseline/case_001.mp4",
                                "video_results": 0.82,
                            },
                        ],
                        "imaging_quality": [
                            {
                                "video_path": "outputs/ours/case_001.mp4",
                                "video_results": 61.5,
                            },
                            {
                                "video_path": "outputs/baseline/case_001.mp4",
                                "video_results": 57.0,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            # Shape B: VBench's [average, entries] tuple, plus an unregistered
            # dimension and an errored record that must be ignored.
            (results / "run_quality_eval_results.json").write_text(
                json.dumps(
                    {
                        "aesthetic_quality": [
                            0.5,
                            [
                                {
                                    "video_path": "outputs/ours/case_001.mp4",
                                    "video_results": 0.52,
                                },
                                {
                                    "video_path": "outputs/baseline/case_001.mp4",
                                    "video_results": 0.47,
                                },
                                {
                                    "video_path": "outputs/baseline/case_001.mp4",
                                    "error": "decode failed",
                                },
                            ],
                        ],
                        "human_action": [
                            {
                                "video_path": "outputs/ours/case_001.mp4",
                                "video_results": 0.9,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output = directory / "evidence.json"
            completed = self.run_adapter(
                [
                    "--manifest",
                    str(manifest),
                    "--results",
                    str(results),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["schema_version"], "1.0")
            self.assertEqual(
                set(evidence["metric_info"]),
                {
                    "vbench_motion_smoothness",
                    "vbench_imaging_quality",
                    "vbench_aesthetic_quality",
                },
            )
            self.assertEqual(len(evidence["cases"]), 2)
            by_method = {
                item["method_id"]: item["metrics"] for item in evidence["cases"]
            }
            self.assertAlmostEqual(
                by_method["ours"]["vbench_motion_smoothness"], 0.91
            )
            self.assertAlmostEqual(
                by_method["baseline"]["vbench_aesthetic_quality"], 0.47
            )
            self.assertIn("human_action", completed.stdout)

    def test_unmatched_records_fail_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest = write_manifest(directory, ["ours"], ["case_001"])
            results = directory / "vbench_results.json"
            results.write_text(
                json.dumps(
                    {
                        "motion_smoothness": [
                            {"video_path": "unknown.mp4", "video_results": 0.5}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            completed = self.run_adapter(
                [
                    "--manifest",
                    str(manifest),
                    "--results",
                    str(results),
                    "--output",
                    str(directory / "out.json"),
                ]
            )
            self.assertEqual(completed.returncode, 1)
            self.assertFalse((directory / "out.json").exists())


class MergeIntegrationTest(unittest.TestCase):
    def test_vbench_evidence_merges_into_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest = write_manifest(directory, ["ours", "baseline"], ["case_001"])
            results = directory / "vbench_results.json"
            results.write_text(
                json.dumps(
                    {
                        "motion_smoothness": [
                            {
                                "video_path": "outputs/ours/case_001.mp4",
                                "video_results": 0.9,
                            },
                            {
                                "video_path": "outputs/baseline/case_001.mp4",
                                "video_results": 0.8,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            evidence = directory / "evidence.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "vbench_import.py"),
                    "--manifest",
                    str(manifest),
                    "--results",
                    str(results),
                    "--output",
                    str(evidence),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            metrics = {
                "schema_version": "1.0",
                "manifest_sha256": "test",
                "experiment": {"split": "test", "blind_seed": 2026},
                "methods": [
                    {"id": "ours", "label": "Ours"},
                    {"id": "baseline", "label": "Baseline"},
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
                        "methods": {
                            "ours": {"valid": True, "metrics": {"ssim": 0.9}},
                            "baseline": {"valid": True, "metrics": {"ssim": 0.8}},
                        },
                    }
                ],
            }
            metrics_path = directory / "metrics.json"
            metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
            merged_path = directory / "merged.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "merge_metrics.py"),
                    "--metrics",
                    str(metrics_path),
                    "--evidence",
                    str(evidence),
                    "--output",
                    str(merged_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            merged = json.loads(merged_path.read_text(encoding="utf-8"))
            summary = merged["aggregates"]["ours"]["vbench_motion_smoothness"]
            self.assertAlmostEqual(summary["mean"], 0.9)
            self.assertEqual(
                merged["metric_info"]["vbench_motion_smoothness"]["dimension"],
                "motion",
            )
            self.assertTrue(
                merged["metric_info"]["vbench_motion_smoothness"][
                    "higher_is_better"
                ]
            )


class RegistryTest(unittest.TestCase):
    def test_registry_entries_are_complete(self) -> None:
        for metric_id, info in EXTERNAL_METRIC_INFO.items():
            with self.subTest(metric=metric_id):
                self.assertTrue(info["label"])
                self.assertIn(
                    info["dimension"],
                    {"style", "content", "temporal", "motion", "quality", "cost"},
                )
                self.assertIsInstance(info["higher_is_better"], bool)


if __name__ == "__main__":
    unittest.main()
