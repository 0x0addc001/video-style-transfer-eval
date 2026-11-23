"""Shared helpers for adapters that import external metric implementations.

Both ``csd_consistency.py`` and ``vbench_import.py`` need the same three
things: resolve manifest outputs to ``(case_id, method_id)`` pairs, describe the
fixed external implementation, and write the evidence JSON that
``merge_metrics.py`` consumes (``schema_version`` 1.0).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from metric_registry import EXTERNAL_METRIC_INFO


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> tuple[dict[str, Any], Path]:
    """Return the parsed manifest and the directory its relative paths use."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0":
        raise ValueError(f"{path}: schema_version must be '1.0'.")
    if not isinstance(manifest.get("cases"), list):
        raise ValueError(f"{path}: missing 'cases' list.")
    return manifest, path.resolve().parent


def resolve_output_video(manifest_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (manifest_dir / path)


def iter_case_outputs(
    manifest: dict[str, Any],
    manifest_dir: Path,
) -> Iterator[tuple[str, str, Path]]:
    """Yield ``(case_id, method_id, video_path)`` for every manifest output."""
    for case in manifest.get("cases", []):
        case_id = case.get("id")
        for method_id, output in (case.get("outputs") or {}).items():
            video = (output or {}).get("video")
            if not case_id or not video:
                continue
            yield case_id, method_id, resolve_output_video(manifest_dir, video)


def build_video_lookup(
    manifest: dict[str, Any],
    manifest_dir: Path,
) -> dict[str, tuple[str, str]]:
    """Map resolved paths and unambiguous path tails to ``(case_id, method_id)``.

    Basenames are only registered when unique: two methods usually share the
    same clip name (``case_001.mp4``) in different directories, and silently
    picking one of them would attach metrics to the wrong method.
    """
    entries: list[tuple[str, str, Path]] = []
    for case_id, method_id, path in iter_case_outputs(manifest, manifest_dir):
        entries.append((case_id, method_id, path))

    lookup: dict[str, tuple[str, str]] = {}
    candidates: dict[str, tuple[str, str]] = {}
    counts: dict[str, int] = {}
    for case_id, method_id, path in entries:
        value = (case_id, method_id)
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = path.as_posix()
        lookup[resolved] = value
        lookup[path.as_posix()] = value
        for key in (path.name, "/".join(path.as_posix().split("/")[-2:])):
            counts[key] = counts.get(key, 0) + 1
            candidates[key] = value
    for key, count in counts.items():
        if count == 1:
            lookup[key] = candidates[key]
    return lookup


def match_video(
    lookup: dict[str, tuple[str, str]],
    reported_path: str,
) -> tuple[str, str] | None:
    """Find the manifest entry for a path reported by an external tool."""
    if not reported_path:
        return None
    candidate = Path(reported_path)
    try:
        resolved = str(candidate.resolve())
    except OSError:
        resolved = ""
    for key in (resolved, candidate.as_posix(), str(candidate), candidate.name):
        if key and key in lookup:
            return lookup[key]
    # VBench sometimes prefixes paths with a directory the manifest omits, so
    # fall back to a suffix match on the longer, still-unambiguous keys.
    normalized = candidate.as_posix().lstrip("./")
    best: tuple[int, tuple[str, str]] | None = None
    for key, value in lookup.items():
        if "/" not in key:
            continue
        if normalized.endswith(key):
            length = len(key)
            if best is None or length > best[0]:
                best = (length, value)
    return best[1] if best else None


def metric_info_for(metric_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Collect registry metadata for the metrics actually emitted."""
    info: dict[str, dict[str, Any]] = {}
    for metric_id in metric_ids:
        if metric_id not in EXTERNAL_METRIC_INFO:
            raise KeyError(
                f"Metric '{metric_id}' is not registered in metric_registry.py. "
                "Add it before emitting evidence for it."
            )
        info[metric_id] = dict(EXTERNAL_METRIC_INFO[metric_id])
    return info


def write_evidence(
    path: Path,
    cases: list[dict[str, Any]],
    implementation: dict[str, Any],
) -> dict[str, Any]:
    """Write a schema 1.0 evidence file and return the serialized payload."""
    if not cases:
        raise ValueError("Refusing to write an evidence file with no cases.")
    metric_ids: list[str] = []
    for item in cases:
        for metric_id in item.get("metrics", {}):
            if metric_id not in metric_ids:
                metric_ids.append(metric_id)
    payload = {
        "schema_version": "1.0",
        "metric_implementation": implementation,
        "metric_info": metric_info_for(metric_ids),
        "cases": cases,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def select_frame_indices(frame_count: int, max_frames: int) -> list[int]:
    """Pick evenly spaced frame indices, always including the first frame."""
    if frame_count <= 0:
        return []
    if max_frames <= 0:
        raise ValueError("max_frames must be positive.")
    if frame_count <= max_frames:
        return list(range(frame_count))
    step = (frame_count - 1) / (max_frames - 1) if max_frames > 1 else frame_count
    indices = sorted({int(round(index * step)) for index in range(max_frames)})
    indices[0] = 0
    return indices
