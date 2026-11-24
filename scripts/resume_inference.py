#!/usr/bin/env python3
"""Resume a batch inference run and record per-clip inference time.

EchoStyle-style inference scripts take a JSON list of clips and write one video
per clip. When a job is preempted or you simply stop early, rerunning the whole
list wastes GPU hours. This wrapper:

1. reads the input list;
2. skips clips whose output already exists under ``--output-dir``;
3. writes the pending subset to ``pending.json``;
4. optionally runs a command template over that subset;
5. records wall-clock timing and per-clip timings (from output mtimes) in
   ``timings.json``.

Example:

    python scripts/resume_inference.py \
      --input scripts/test_10.json \
      --output-dir results/demo \
      --command "PYTHONPATH=. torchrun --nproc_per_node=8 --standalone \
                 trainer/models/wan22/eval.py --task i2v-A14B ... \
                 --data_path {input} --output_dir {output}" \
      --command-dir EchoStyle

The output pattern defaults to ``{stem}_gen.mp4`` (01.mp4 → 01_gen.mp4).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--output-pattern",
        default="{stem}_gen.mp4",
        help="Output filename pattern used by the inference script.",
    )
    parser.add_argument(
        "--command",
        help="Optional shell command template; {input} and {output} are replaced.",
    )
    parser.add_argument(
        "--command-dir",
        type=Path,
        help="Working directory for the command (e.g. the EchoStyle checkout).",
    )
    parser.add_argument(
        "--keep-pending",
        action="store_true",
        help="Keep pending.json after a successful run.",
    )
    return parser.parse_args()


def expected_output(
    item: dict[str, Any], output_dir: Path, pattern: str
) -> Path:
    source = item.get("src_video_path") or item.get("video") or ""
    stem = Path(str(source)).stem or "clip"
    return output_dir / pattern.format(stem=stem)


def split_pending(
    items: list[dict[str, Any]], output_dir: Path, pattern: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pending, done = [], []
    for item in items:
        if expected_output(item, output_dir, pattern).is_file():
            done.append(item)
        else:
            pending.append(item)
    return pending, done


def main() -> int:
    args = parse_args()
    items = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        print("--input must contain a JSON list of clips", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)

    pending, done = split_pending(items, args.output_dir, args.output_pattern)
    print(
        f"{len(items)} clips: {len(done)} already done, {len(pending)} pending"
    )
    if not pending:
        return 0

    pending_path = args.output_dir / "pending.json"
    pending_path.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    started_at = time.time()
    if args.command:
        command = args.command.format(
            input=str(pending_path.resolve()),
            output=str(args.output_dir.resolve()),
        )
        print(f"$ {command}")
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(args.command_dir) if args.command_dir else None,
            check=False,
        )
        if completed.returncode != 0:
            print(
                f"command failed with exit code {completed.returncode}; "
                "outputs already written are kept, rerun to resume.",
                file=sys.stderr,
            )
    elapsed = time.time() - started_at

    timings: list[dict[str, Any]] = []
    previous_mtime = started_at
    for item in pending:
        output = expected_output(item, args.output_dir, args.output_pattern)
        if not output.is_file():
            continue
        mtime = output.stat().st_mtime
        timings.append(
            {
                "case": Path(
                    str(item.get("src_video_path") or item.get("video") or "")
                ).stem,
                "output": str(output),
                "inference_s": round(max(0.0, mtime - previous_mtime), 2),
            }
        )
        previous_mtime = mtime
    summary = {
        "total_clips": len(items),
        "skipped_as_done": len(done),
        "pending": len(pending),
        "completed": len(timings),
        "wall_clock_s": round(elapsed, 2),
        "mean_inference_s": (
            round(sum(t["inference_s"] for t in timings) / len(timings), 2)
            if timings
            else None
        ),
        "per_clip": timings,
    }
    (args.output_dir / "timings.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not args.keep_pending:
        pending_path.unlink(missing_ok=True)
    print(
        f"done: {len(timings)} clips in {elapsed:.1f}s "
        f"(mean {summary['mean_inference_s']}s/clip); timings.json written"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
