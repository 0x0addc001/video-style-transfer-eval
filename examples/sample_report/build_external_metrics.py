#!/usr/bin/env python3
"""Build clearly labelled synthetic CSD/VBench evidence for the demo report.

The sample report demonstrates the full workflow, including the external metric
merge path. EchoStyle-style CSD scores and VBench dimensions cannot be computed
on synthetic clips without a GPU model zoo, so this script fabricates plausible
values with a fixed seed. Every value is synthetic and the evidence file says so
in ``metric_implementation``.

    python examples/sample_report/build_external_metrics.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from metric_registry import EXTERNAL_METRIC_INFO  # noqa: E402


#: Base values per simulated method. They follow the demo story: the balanced
#: method is temporally stable, the flicker method trades stability for style,
#: and the overlay method is blurry with the lowest image quality.
METHOD_BASE = {
    "balanced": {
        "csd_s": 0.932,
        "csd_c": 0.901,
        "vbench_subject_consistency": 0.941,
        "vbench_background_consistency": 0.952,
        "vbench_temporal_flickering": 0.968,
        "vbench_motion_smoothness": 0.979,
        "vbench_dynamic_degree": 0.667,
        "vbench_aesthetic_quality": 0.521,
        "vbench_imaging_quality": 61.8,
    },
    "flicker": {
        "csd_s": 0.818,
        "csd_c": 0.842,
        "vbench_subject_consistency": 0.833,
        "vbench_background_consistency": 0.861,
        "vbench_temporal_flickering": 0.781,
        "vbench_motion_smoothness": 0.902,
        "vbench_dynamic_degree": 0.667,
        "vbench_aesthetic_quality": 0.446,
        "vbench_imaging_quality": 54.2,
    },
    "overlay": {
        "csd_s": 0.874,
        "csd_c": 0.803,
        "vbench_subject_consistency": 0.897,
        "vbench_background_consistency": 0.882,
        "vbench_temporal_flickering": 0.921,
        "vbench_motion_smoothness": 0.949,
        "vbench_dynamic_degree": 0.667,
        "vbench_aesthetic_quality": 0.403,
        "vbench_imaging_quality": 48.6,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).parent / "demo_run" / "manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent
        / "demo_evaluation"
        / "external_metrics_synthetic.json",
    )
    return parser.parse_args()


def jitter(case_id: str, method_id: str, metric: str) -> float:
    """Deterministic, tiny offset in [-1, 1] so cases are not identical."""
    digest = hashlib.sha256(f"{case_id}|{method_id}|{metric}".encode()).digest()
    return (digest[0] / 255.0) * 2.0 - 1.0


def synthetic_value(
    case_id: str,
    method_id: str,
    metric: str,
    base: float,
) -> float:
    spans = {
        "vbench_imaging_quality": 2.5,
        "vbench_dynamic_degree": 0.08,
        "vbench_aesthetic_quality": 0.03,
    }
    span = spans.get(metric, 0.02)
    return round(max(0.0, min(base + jitter(case_id, method_id, metric) * span, 100.0)), 4)


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = []
    for case in manifest["cases"]:
        case_id = case["id"]
        for method_id in case["outputs"]:
            base = METHOD_BASE[method_id]
            cases.append(
                {
                    "case_id": case_id,
                    "method_id": method_id,
                    "metrics": {
                        metric: synthetic_value(
                            case_id, method_id, metric, value
                        )
                        for metric, value in base.items()
                    },
                }
            )

    payload = {
        "schema_version": "1.0",
        "metric_implementation": {
            "name": "Synthetic CSD/VBench stand-in for the workflow demo",
            "version_or_commit": f"fixed synthetic values from {Path(__file__).name}",
            "device": "none",
            "resolution": "not applicable",
            "notes": (
                "Every value in this file is fabricated to demonstrate the merge "
                "and report path. Do not cite it as a measurement of EchoStyle or "
                "any real model."
            ),
        },
        "metric_info": {
            metric: dict(EXTERNAL_METRIC_INFO[metric])
            for metric in METHOD_BASE["balanced"]
        },
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(cases)} synthetic case records to {args.output}")


if __name__ == "__main__":
    main()
