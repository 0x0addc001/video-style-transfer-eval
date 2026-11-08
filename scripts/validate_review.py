#!/usr/bin/env python3
"""Validate blinded VLM/human reviews and produce an unmasked review export."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any


SCORE_DIMENSIONS = [
    "style_adherence",
    "content_preservation",
    "temporal_stability",
    "artifact_control",
    "overall_visual_quality",
]
PREFERENCE_DIMENSIONS = [
    "style_adherence",
    "content_preservation",
    "temporal_stability",
    "artifact_control",
    "overall_visual_quality",
]
CONFIDENCE_VALUES = {"low", "medium", "high"}
FAILURE_TAGS = {
    "flicker",
    "texture_sticking",
    "texture_drift",
    "identity_drift",
    "geometry_melting",
    "edge_ghosting",
    "occlusion_break",
    "new_region_error",
    "motion_duplication",
    "temporal_jump",
    "color_bleed",
    "banding",
    "detail_loss",
    "reference_copied",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review",
        required=True,
        nargs="+",
        help="One or more review JSON files or glob patterns.",
    )
    parser.add_argument("--blind-map", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON path. Defaults next to the blind map.",
    )
    return parser.parse_args()


def expand_review_paths(values: list[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        candidate = Path(value)
        if candidate.is_file():
            paths.append(candidate.resolve())
            continue
        matches = [Path(match).resolve() for match in glob.glob(value)]
        if not matches:
            raise FileNotFoundError(f"Review file or pattern matched nothing: {value}")
        paths.extend(matches)
    return sorted(set(paths))


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_review(
    review: dict[str, Any],
    blind_map: dict[str, dict[str, str]],
    source_path: Path,
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    require(review.get("schema_version") == "1.0", "schema_version must be '1.0'.", errors)
    reviewer = review.get("reviewer")
    require(isinstance(reviewer, dict), "reviewer must be an object.", errors)
    reviewer = reviewer if isinstance(reviewer, dict) else {}
    for field in ("id", "type", "model", "review_date", "input_scope"):
        value = reviewer.get(field)
        require(
            isinstance(value, str) and bool(value.strip()),
            f"reviewer.{field} must be a non-empty string.",
            errors,
        )
    require(reviewer.get("blind") is True, "reviewer.blind must be true.", errors)

    seen_scores: set[tuple[str, str]] = set()
    unmasked_scores = []
    raw_scores = review.get("scores")
    require(isinstance(raw_scores, list), "scores must be a list.", errors)
    raw_scores = raw_scores if isinstance(raw_scores, list) else []
    for index, score in enumerate(raw_scores):
        prefix = f"scores[{index}]"
        require(isinstance(score, dict), f"{prefix} must be an object.", errors)
        if not isinstance(score, dict):
            continue
        case_id = score.get("case_id")
        blind_id = score.get("method_blind_id")
        require(isinstance(case_id, str), f"{prefix}.case_id is required.", errors)
        require(
            isinstance(blind_id, str),
            f"{prefix}.method_blind_id is required.",
            errors,
        )
        if not isinstance(case_id, str) or not isinstance(blind_id, str):
            continue
        require(
            case_id in blind_map,
            f"{prefix} references unknown case '{case_id}'.",
            errors,
        )
        if case_id not in blind_map:
            continue
        require(
            blind_id in blind_map[case_id],
            f"{prefix} references unknown blind label '{blind_id}' for {case_id}.",
            errors,
        )
        if blind_id not in blind_map[case_id]:
            continue
        key = (case_id, blind_id)
        require(key not in seen_scores, f"{prefix} duplicates {case_id}/{blind_id}.", errors)
        seen_scores.add(key)

        insufficient = score.get("insufficient")
        require(
            isinstance(insufficient, bool),
            f"{prefix}.insufficient must be true or false.",
            errors,
        )
        if insufficient is True:
            warnings.append(f"{prefix} is marked insufficient.")
        elif insufficient is False:
            for dimension in SCORE_DIMENSIONS:
                value = score.get(dimension)
                require(
                    isinstance(value, int) and 1 <= value <= 5,
                    f"{prefix}.{dimension} must be an integer from 1 to 5.",
                    errors,
                )

        confidence = score.get("confidence")
        require(
            confidence in CONFIDENCE_VALUES,
            f"{prefix}.confidence must be low, medium, or high.",
            errors,
        )
        failure_tags = score.get("failure_tags", [])
        require(
            isinstance(failure_tags, list)
            and all(isinstance(tag, str) for tag in failure_tags),
            f"{prefix}.failure_tags must be a list of strings.",
            errors,
        )
        if isinstance(failure_tags, list):
            unknown_tags = sorted(set(failure_tags) - FAILURE_TAGS)
            require(
                not unknown_tags,
                f"{prefix} has unknown failure tags: {unknown_tags}.",
                errors,
            )
        evidence = score.get("evidence", "")
        require(
            isinstance(evidence, str),
            f"{prefix}.evidence must be a string.",
            errors,
        )
        if insufficient is False:
            require(
                isinstance(evidence, str) and len(evidence.strip()) >= 8,
                f"{prefix}.evidence is required for a scored output.",
                errors,
            )
        if confidence == "low" and not str(evidence).strip():
            warnings.append(f"{prefix} has low confidence without evidence.")

        unmasked_scores.append(
            {
                **score,
                "method_id": blind_map[case_id][blind_id],
            }
        )

    raw_preferences = review.get("preferences", [])
    require(
        isinstance(raw_preferences, list),
        "preferences must be a list.",
        errors,
    )
    raw_preferences = raw_preferences if isinstance(raw_preferences, list) else []
    unmasked_preferences = []
    for index, preference in enumerate(raw_preferences):
        prefix = f"preferences[{index}]"
        require(isinstance(preference, dict), f"{prefix} must be an object.", errors)
        if not isinstance(preference, dict):
            continue
        case_id = preference.get("case_id")
        dimension = preference.get("dimension")
        winner = preference.get("winner_blind_id")
        tie = preference.get("tie")
        require(
            isinstance(case_id, str) and case_id in blind_map,
            f"{prefix}.case_id is unknown.",
            errors,
        )
        require(
            dimension in PREFERENCE_DIMENSIONS,
            f"{prefix}.dimension is invalid.",
            errors,
        )
        require(isinstance(tie, bool), f"{prefix}.tie must be true or false.", errors)
        if not isinstance(case_id, str) or case_id not in blind_map:
            continue
        require(
            (tie is True and winner in (None, ""))
            or (tie is False and isinstance(winner, str) and winner in blind_map[case_id]),
            f"{prefix} must name a valid blind winner unless tie is true.",
            errors,
        )
        require(
            preference.get("confidence") in CONFIDENCE_VALUES,
            f"{prefix}.confidence is invalid.",
            errors,
        )
        evidence = preference.get("evidence", "")
        require(
            isinstance(evidence, str) and len(evidence.strip()) >= 8,
            f"{prefix}.evidence is required.",
            errors,
        )
        unmasked_preferences.append(
            {
                **preference,
                "winner_method_id": (
                    None
                    if tie is True or not isinstance(winner, str)
                    else blind_map[case_id].get(winner)
                ),
            }
        )

    expected_scores = {
        (case_id, blind_id)
        for case_id, methods in blind_map.items()
        for blind_id in methods
    }
    missing_scores = sorted(expected_scores - seen_scores)
    if missing_scores:
        warnings.append(f"Missing {len(missing_scores)} expected case/method scores.")

    unmasked = {
        "schema_version": "1.0",
        "source_review": str(source_path.resolve()),
        "reviewer": reviewer,
        "scores": unmasked_scores,
        "preferences": unmasked_preferences,
        "completeness": {
            "expected_scores": len(expected_scores),
            "provided_scores": len(seen_scores),
            "missing_scores": [
                {"case_id": case_id, "method_blind_id": blind_id}
                for case_id, blind_id in missing_scores
            ],
        },
    }
    return unmasked, errors, warnings


def main() -> None:
    args = parse_args()
    review_paths = expand_review_paths(args.review)
    blind_map = json.loads(args.blind_map.read_text(encoding="utf-8"))
    output_path = args.output or (args.blind_map.parent / "validated_reviews.json")

    all_reviews = []
    all_errors: list[str] = []
    all_warnings: list[str] = []
    seen_reviewers: set[str] = set()
    for path in review_paths:
        try:
            review = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            all_errors.append(f"{path}: cannot read JSON: {error}")
            continue
        unmasked, errors, warnings = validate_review(review, blind_map, path)
        reviewer_id = unmasked.get("reviewer", {}).get("id")
        if reviewer_id in seen_reviewers:
            all_errors.append(f"{path}: duplicate reviewer id '{reviewer_id}'.")
        elif isinstance(reviewer_id, str):
            seen_reviewers.add(reviewer_id)
        all_reviews.append(unmasked)
        all_errors.extend(f"{path}: {message}" for message in errors)
        all_warnings.extend(f"{path}: {message}" for message in warnings)

    if all_errors:
        for message in all_errors:
            print(f"ERROR: {message}")
        raise SystemExit(1)

    output = {
        "schema_version": "1.0",
        "blind_map": str(args.blind_map.resolve()),
        "reviewer_count": len(all_reviews),
        "reviews": all_reviews,
        "warnings": all_warnings,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Validated {len(all_reviews)} review file(s): {output_path}")
    for warning in all_warnings:
        print(f"WARNING: {warning}")


if __name__ == "__main__":
    main()
