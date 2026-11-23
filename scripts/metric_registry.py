"""Registry for metrics computed outside the deterministic diagnostic pass.

The diagnostic pass in ``evaluate.py`` is intentionally cheap and torch-free.
Paper-grade evidence comes from fixed external implementations (CSD, VBench,
LPIPS/CLIP, RAFT) and is merged into the same run through ``merge_metrics.py``.

Keeping the metadata here means the merge step, the adapters
(``csd_consistency.py``, ``vbench_import.py``) and the report agree on the label,
dimension, preferred direction and unit of every external metric.
"""

from __future__ import annotations

from typing import Any


#: Metadata for externally computed metrics that this skill knows how to merge.
#: ``dimension`` is one of ``style``, ``content``, ``temporal``, ``motion``,
#: ``quality`` or ``cost``; ``higher_is_better`` drives table ordering, the
#: direction arrow and the paired-effect sign convention.
EXTERNAL_METRIC_INFO: dict[str, dict[str, Any]] = {
    "csd_s": {
        "label": "CSD-S style consistency",
        "dimension": "style",
        "higher_is_better": True,
        "unit": "cosine",
    },
    "csd_c": {
        "label": "CSD-C content consistency",
        "dimension": "content",
        "higher_is_better": True,
        "unit": "cosine",
    },
    "vbench_subject_consistency": {
        "label": "VBench subject consistency",
        "dimension": "temporal",
        "higher_is_better": True,
        "unit": "0-1",
    },
    "vbench_background_consistency": {
        "label": "VBench background consistency",
        "dimension": "temporal",
        "higher_is_better": True,
        "unit": "0-1",
    },
    "vbench_temporal_flickering": {
        "label": "VBench temporal flickering",
        "dimension": "temporal",
        "higher_is_better": True,
        "unit": "0-1",
    },
    "vbench_motion_smoothness": {
        "label": "VBench motion smoothness",
        "dimension": "motion",
        "higher_is_better": True,
        "unit": "0-1",
    },
    "vbench_dynamic_degree": {
        "label": "VBench dynamic degree",
        "dimension": "motion",
        "higher_is_better": True,
        "unit": "0-1",
    },
    "vbench_aesthetic_quality": {
        "label": "VBench aesthetic quality",
        "dimension": "quality",
        "higher_is_better": True,
        "unit": "0-1",
    },
    "vbench_imaging_quality": {
        "label": "VBench imaging quality",
        "dimension": "quality",
        "higher_is_better": True,
        "unit": "MUSIQ 0-100",
    },
}

#: Canonical IDs of the CSD-based metrics emitted by ``csd_consistency.py``.
CSD_METRICS = ("csd_s", "csd_c")

#: Canonical IDs of the VBench dimensions emitted by ``vbench_import.py``.
VBENCH_METRICS = (
    "vbench_subject_consistency",
    "vbench_background_consistency",
    "vbench_temporal_flickering",
    "vbench_motion_smoothness",
    "vbench_dynamic_degree",
    "vbench_aesthetic_quality",
    "vbench_imaging_quality",
)


def metric_info(metric_id: str) -> dict[str, Any]:
    """Return a defensive copy of the registered metadata for ``metric_id``."""
    if metric_id not in EXTERNAL_METRIC_INFO:
        raise KeyError(f"Unknown external metric: {metric_id}")
    return dict(EXTERNAL_METRIC_INFO[metric_id])
