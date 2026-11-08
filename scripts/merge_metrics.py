#!/usr/bin/env python3
"""Merge externally computed paper-grade metrics into a diagnostic metric run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluate import aggregate_results


DEFAULT_METRIC_INFO = {
    "lpips": {
        "label": "LPIPS",
        "dimension": "content",
        "higher_is_better": False,
        "unit": "",
    },
    "clip_i": {
        "label": "CLIP-I",
        "dimension": "style",
        "higher_is_better": True,
        "unit": "",
    },
    "clip_f": {
        "label": "CLIP-F",
        "dimension": "content",
        "higher_is_better": True,
        "unit": "",
    },
    "fid": {
        "label": "FID",
        "dimension": "style",
        "higher_is_better": False,
        "unit": "",
    },
    "artfid": {
        "label": "ArtFID",
        "dimension": "style",
        "higher_is_better": False,
        "unit": "",
    },
    "tlp": {
        "label": "tLP",
        "dimension": "temporal",
        "higher_is_better": False,
        "unit": "",
    },
    "clip_cons": {
        "label": "CLIP-CONS",
        "dimension": "motion",
        "higher_is_better": True,
        "unit": "",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument(
        "--evidence",
        required=True,
        nargs="+",
        help="One or more external metric JSON files.",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    known_methods = {method["id"] for method in metrics.get("methods", [])}
    known_cases = {case["id"]: case for case in metrics.get("cases", [])}
    metric_info = metrics.setdefault("metric_info", {})

    merged_count = 0
    evidence_paths = [Path(value) for value in args.evidence]
    for evidence_path in evidence_paths:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence.get("schema_version") != "1.0":
            raise ValueError(f"{evidence_path}: schema_version must be '1.0'.")
        for metric, default_info in DEFAULT_METRIC_INFO.items():
            if metric in evidence.get("metric_info", {}):
                metric_info[metric] = evidence["metric_info"][metric]
            elif any(
                metric in item.get("metrics", {})
                for item in evidence.get("cases", [])
            ):
                metric_info.setdefault(metric, default_info)
        for custom_metric, info in evidence.get("metric_info", {}).items():
            metric_info[custom_metric] = info

        for item in evidence.get("cases", []):
            case_id = item.get("case_id")
            method_id = item.get("method_id")
            values = item.get("metrics", {})
            if case_id not in known_cases:
                raise ValueError(f"{evidence_path}: unknown case '{case_id}'.")
            if method_id not in known_methods:
                raise ValueError(f"{evidence_path}: unknown method '{method_id}'.")
            result = known_cases[case_id].get("methods", {}).get(method_id)
            if not result or not result.get("valid"):
                raise ValueError(
                    f"{evidence_path}: cannot attach metrics to invalid "
                    f"{case_id}/{method_id}."
                )
            result.setdefault("metrics", {}).update(values)
            merged_count += len(values)

    cases = metrics.get("cases", [])
    method_order = [method["id"] for method in metrics.get("methods", [])]
    seed = int(metrics.get("experiment", {}).get("blind_seed", 2026))
    aggregates, pairwise = aggregate_results(cases, method_order, seed)
    metrics["aggregates"] = aggregates
    metrics["pairwise"] = pairwise
    metrics.setdefault("evidence_merge", {})["files"] = [
        {
            "path": str(path.resolve()),
            "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
            "metric_implementation": json.loads(
                path.read_text(encoding="utf-8")
            ).get("metric_implementation"),
        }
        for path in evidence_paths
    ]
    metrics["evidence_merge"]["metric_value_count"] = merged_count

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Merged {merged_count} metric values into {args.output}")


if __name__ == "__main__":
    main()
