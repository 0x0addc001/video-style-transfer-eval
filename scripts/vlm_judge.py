#!/usr/bin/env python3
"""Generate blinded VLM review scores with Gemini or Qwen-VL.

The judge reads the contact sheets produced by ``evaluate.py`` (blinded labels
M1..Mn), asks the model for the five rubric dimensions on a 1-5 scale plus
failure tags, and writes a review file in the schema expected by
``validate_review.py``.

    python scripts/vlm_judge.py \
      --blind-map evaluation_run/review_packet/blind_map.json \
      --contact-sheets evaluation_run/contact_sheets \
      --provider qwen --model qwen-vl-max \
      --output reviews/vlm_qwen.json

    python scripts/vlm_judge.py ... --provider gemini --model gemini-2.5-flash

API keys are read from ``DASHSCOPE_API_KEY`` (qwen) or ``GEMINI_API_KEY``
(gemini). Use ``--dry-run`` to write the prompts without calling the API.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

SCORE_DIMENSIONS = (
    "style_adherence",
    "content_preservation",
    "temporal_stability",
    "artifact_control",
    "overall_visual_quality",
)
FAILURE_TAGS = (
    "flicker",
    "temporal_jump",
    "texture_sticking",
    "detail_loss",
    "color_bleed",
    "geometric_distortion",
    "reference_copied",
    "banding",
    "edge_ghosting",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blind-map", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Manifest used to read each case's style instruction for the judge.",
    )
    parser.add_argument("--contact-sheets", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--provider", choices=("gemini", "qwen"), default="qwen")
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path("~/.config/video-style-transfer-eval/env").expanduser(),
        help="Optional KEY=VALUE file with DASHSCOPE_API_KEY / GEMINI_API_KEY.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reviewer-id", default="vlm-judge")
    return parser.parse_args()


def build_prompt(
    case_id: str,
    labels: list[str],
    style_prompt: str | None = None,
) -> str:
    label_list = ", ".join(labels)
    style_line = (
        f"The requested style/instruction is: {style_prompt}. "
        if style_prompt
        else ""
    )
    return (
        "You are a blinded reviewer of video style-transfer results. The image "
        "is a contact sheet: the STYLE reference (if present), several SOURCE "
        f"frames, and {len(labels)} candidate rows labelled {label_list}. "
        f"{style_line}"
        "Judge each candidate independently on five 1-5 scales: style_adherence, "
        "content_preservation, temporal_stability, artifact_control, "
        "overall_visual_quality. Return strict JSON with this shape:\n"
        '{"scores": [{"method_blind_id": "M1", "style_adherence": 4, '
        '"content_preservation": 4, "temporal_stability": 3, '
        '"artifact_control": 3, "overall_visual_quality": 4, '
        '"confidence": "medium", "failure_tags": ["flicker"], '
        '"evidence": "short visual evidence", "comments": "one sentence"}]}\n'
        f"Allowed failure tags: {', '.join(FAILURE_TAGS)}. "
        "Use an empty failure_tags list when nothing applies. "
        f"Case id: {case_id}. Return JSON only."
    )


def encode_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def call_gemini(model: str, prompt: str, image_b64: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. The Gemini API is region-restricted and "
            "is not available in Hong Kong; use --provider qwen instead."
        )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_b64,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"response_mime_type": "application/json"},
    }
    return post_json(url, payload, {})


def call_qwen(model: str, prompt: str, image_b64: str) -> str:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not set")
    base_url = os.environ.get(
        "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ).rstrip("/")
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
        "response_format": {"type": "json_object"},
    }
    raw = post_json(url, payload, {"Authorization": f"Bearer {api_key}"})
    body = json.loads(raw)
    return body["choices"][0]["message"]["content"]


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    if "candidates" in body:
        return body["candidates"][0]["content"]["parts"][0]["text"]
    return json.dumps(body)


def parse_scores(raw: str, case_id: str, labels: list[str]) -> list[dict[str, Any]]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    payload = json.loads(text)
    scores = []
    for item in payload.get("scores", []):
        label = item.get("method_blind_id")
        if label not in labels:
            continue
        record: dict[str, Any] = {
            "case_id": case_id,
            "method_blind_id": label,
            "insufficient": False,
        }
        for dimension in SCORE_DIMENSIONS:
            value = int(item.get(dimension, 3))
            record[dimension] = max(1, min(5, value))
        record["confidence"] = str(item.get("confidence", "medium"))
        tags = [
            tag
            for tag in item.get("failure_tags", [])
            if tag in FAILURE_TAGS
        ]
        record["failure_tags"] = tags
        record["evidence"] = str(item.get("evidence", "VLM visual assessment."))
        record["comments"] = str(item.get("comments", ""))
        scores.append(record)
    return scores


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE lines without overriding the real environment."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    args = parse_args()
    load_env_file(args.env_file)
    blind_map = json.loads(args.blind_map.read_text(encoding="utf-8"))
    style_prompts: dict[str, str] = {}
    if args.manifest:
        manifest_data = json.loads(args.manifest.read_text(encoding="utf-8"))
        for case in manifest_data.get("cases", []):
            prompt = (
                case.get("style_prompt")
                or case.get("prompt")
                or case.get("style_id")
                or ""
            )
            if prompt:
                style_prompts[str(case.get("id"))] = str(prompt)
    model = args.model or ("gemini-2.5-flash" if args.provider == "gemini" else "qwen-vl-max")
    reviews: list[dict[str, Any]] = []
    cases = list(blind_map.items())
    if args.limit:
        cases = cases[: args.limit]

    for case_id, label_map in cases:
        labels = sorted(label_map)
        prompt = build_prompt(case_id, labels, style_prompts.get(case_id))
        sheet = args.contact_sheets / f"{case_id}.jpg"
        if not sheet.is_file():
            print(f"[skip] missing contact sheet: {sheet}", file=sys.stderr)
            continue
        if args.dry_run:
            print(f"[dry-run] {case_id}: {len(labels)} labels, {sheet.name}")
            continue
        image_b64 = encode_image(sheet)
        raw = (
            call_gemini(model, prompt, image_b64)
            if args.provider == "gemini"
            else call_qwen(model, prompt, image_b64)
        )
        try:
            reviews.extend(parse_scores(raw, case_id, labels))
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            print(f"[warn] {case_id}: cannot parse response ({error})", file=sys.stderr)
        print(f"[{case_id}] scored {len(labels)} candidates")

    if args.dry_run:
        return 0

    payload = {
        "schema_version": "1.0",
        "reviewer": {
            "id": args.reviewer_id,
            "type": "vlm",
            "model": model,
            "review_date": date.today().isoformat(),
            "blind": True,
            "input_scope": "contact_sheets_only",
        },
        "scores": reviews,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(reviews)} scores to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
