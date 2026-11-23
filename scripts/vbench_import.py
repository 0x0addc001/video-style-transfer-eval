#!/usr/bin/env python3
"""Import VBench per-video results into the skill's evidence schema.

VBench (Huang et al., "VBench: Comprehensive Benchmark Suite for Video
Generative Models") writes one ``<name>_eval_results.json`` per evaluation run,
mapping a dimension name to a list of ``{"video_path", "video_results"}``
records. This adapter maps those records back to manifest cases and methods so
`merge_metrics.py` can merge them next to the diagnostic metrics.

VBench is normally run on the GPU host:

    vbench evaluate --videos_path outputs/ --dimension motion_smoothness
    vbench evaluate --videos_path outputs/ --dimension imaging_quality

then:

    python scripts/vbench_import.py \
      --manifest evaluation/manifest.json \
      --results evaluation/vbench_results \
      --output evaluation/evidence/vbench.json

Only dimensions registered in `metric_registry.py` are imported; unknown
dimensions are reported and skipped instead of being silently mislabelled.
Records must be produced in VBench ``custom_input`` mode, so the numbers are not
comparable to the official leaderboard (which uses the fixed prompt suite).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable

from evidence_io import (
    build_video_lookup,
    load_manifest,
    match_video,
    write_evidence,
)
from metric_registry import VBENCH_METRICS


DIMENSION_TO_METRIC = {metric: metric for metric in VBENCH_METRICS}
#: VBench dimension names are the metric suffix; accept both spellings.
DIMENSION_TO_METRIC.update(
    {
        metric.removeprefix("vbench_"): metric
        for metric in VBENCH_METRICS
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--results",
        required=True,
        nargs="+",
        type=Path,
        help="VBench output files or directories containing *_eval_results.json.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--dimensions",
        nargs="*",
        default=None,
        help="Optional subset of VBench dimensions to import.",
    )
    return parser.parse_args()


def collect_result_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*_eval_results.json")))
            files.extend(sorted(path.glob("*.json")))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"VBench results path not found: {path}")
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def result_entries(payload: Any) -> list[dict[str, Any]]:
    """Return per-video entries from the shapes VBench and wrappers emit."""
    if isinstance(payload, dict):
        for key in ("video_results", "results", "entries"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []
    if isinstance(payload, list):
        # VBench's evaluate() returns (average, video_results) for some
        # dimensions; json.dump then stores [average, [entry, ...]].
        if payload and isinstance(payload[0], (int, float)):
            for item in payload[1:]:
                if isinstance(item, list):
                    return [entry for entry in item if isinstance(entry, dict)]
            return []
        return [item for item in payload if isinstance(item, dict)]
    return []


def entry_path(entry: dict[str, Any]) -> str:
    for key in ("video_path", "video", "path", "name"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def entry_score(entry: dict[str, Any]) -> float | None:
    if entry.get("error"):
        return None
    for key in ("video_results", "score", "value"):
        if key not in entry:
            continue
        try:
            value = float(entry[key])
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None
    return None


def main() -> int:
    args = parse_args()
    manifest, manifest_dir = load_manifest(args.manifest)
    lookup = build_video_lookup(manifest, manifest_dir)
    wanted = None
    if args.dimensions:
        wanted = set(args.dimensions)

    files = collect_result_files(args.results)
    if not files:
        print("No VBench result files were found.", file=sys.stderr)
        return 1

    values: dict[tuple[str, str], dict[str, list[float]]] = {}
    skipped_dimensions: set[str] = set()
    unmatched: list[str] = []
    matched_records = 0

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            print(f"[skip] {path}: not a VBench dimension mapping")
            continue
        for dimension, dimension_payload in payload.items():
            if wanted is not None and dimension not in wanted:
                continue
            metric_id = DIMENSION_TO_METRIC.get(dimension)
            if metric_id is None:
                skipped_dimensions.add(dimension)
                continue
            for entry in result_entries(dimension_payload):
                score = entry_score(entry)
                if score is None:
                    continue
                reported = entry_path(entry)
                match = match_video(lookup, reported)
                if match is None:
                    unmatched.append(f"{dimension}: {reported}")
                    continue
                case_id, method_id = match
                values.setdefault((case_id, method_id), {}).setdefault(
                    metric_id, []
                ).append(score)
                matched_records += 1

    if not values:
        print(
            "No VBench records matched a manifest output. Check that the "
            "results were computed on the manifest videos and that the paths "
            "share a filename.",
            file=sys.stderr,
        )
        return 1

    order = [
        (case.get("id"), method_id)
        for case in manifest.get("cases", [])
        for method_id in (case.get("outputs") or {})
    ]
    evidence_cases: list[dict[str, Any]] = []
    for key in order:
        metric_values = values.get(key)
        if not metric_values:
            continue
        metrics = {
            metric_id: round(sum(scores) / len(scores), 6)
            for metric_id, scores in metric_values.items()
        }
        evidence_cases.append(
            {
                "case_id": key[0],
                "method_id": key[1],
                "metrics": metrics,
            }
        )

    implementation = {
        "name": "VBench (custom_input mode, per-dimension evaluators)",
        "version_or_commit": "VBench main branch; record the exact commit",
        "device": "cuda",
        "resolution": "native clip resolution as decoded by VBench",
        "notes": (
            "Scores are VBench custom_input results averaged per clip and frame "
            "as implemented by VBench. They are not comparable with the official "
            "VBench leaderboard, which uses its fixed prompt suite. Use the same "
            "VBench commit for every compared method."
        ),
    }
    write_evidence(args.output, evidence_cases, implementation)
    print(
        f"Matched {matched_records} VBench records into {len(evidence_cases)} "
        f"case/method rows -> {args.output}"
    )
    if unmatched:
        print(
            f"{len(unmatched)} VBench records did not match a manifest output "
            "(showing up to 5):"
        )
        for item in unmatched[:5]:
            print(f"  {item}")
    if skipped_dimensions:
        print(
            "Skipped dimensions that are not registered in metric_registry.py: "
            + ", ".join(sorted(skipped_dimensions))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
