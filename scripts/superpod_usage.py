#!/usr/bin/env python3
"""Estimate SuperPOD spend from Slurm accounting (no balance API exists).

Runs ``sacct`` over SSH, multiplies each job's elapsed time by its allocated
GPUs and the per-GPU-minute rate, and prints a per-job table plus a total.

Example:
    python scripts/superpod_usage.py --since 2026-11-01 --rate 0.2
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

DEFAULT_HOST = "jlior@superpod.ust.hk"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--user", default=None, help="Slurm user; defaults to the SSH user.")
    parser.add_argument("--since", default="2026-11-01")
    parser.add_argument("--rate", type=float, default=0.2, help="HKD per GPU-minute.")
    return parser.parse_args()


def parse_elapsed(text: str) -> int:
    """Return seconds from Slurm's [D-]HH:MM:SS format."""
    days = 0
    if "-" in text:
        day_part, text = text.split("-", 1)
        days = int(day_part)
    parts = [int(part) for part in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    hours, minutes, seconds = parts
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def main() -> None:
    args = parse_args()
    user = args.user or args.host.split("@", 1)[0]
    remote = (
        "bash -lc 'module load slurm 2>/dev/null; "
        f"sacct -u {user} -S {args.since} -X -P "
        "-o JobID,JobName,Elapsed,AllocTRES'"
    )
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", args.host, remote],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "ssh/sacct failed")

    total_gpu_minutes = 0.0
    print(f"{'JobID':>8}  {'Name':<22} {'GPU':>3}  {'GPU-min':>8}")
    for line in result.stdout.strip().splitlines():
        fields = line.split("|")
        if len(fields) < 4 or fields[0].startswith("JobID"):
            continue
        job_id, name, elapsed, tres = fields[:4]
        gpu_match = re.search(r"gres/gpu=(\d+)", tres)
        if not gpu_match:
            continue
        gpus = int(gpu_match.group(1))
        seconds = parse_elapsed(elapsed)
        gpu_minutes = gpus * seconds / 60.0
        total_gpu_minutes += gpu_minutes
        print(f"{job_id:>8}  {name[:22]:<22} {gpus:>3}  {gpu_minutes:8.1f}")

    print("-" * 50)
    print(f"Total GPU-minutes: {total_gpu_minutes:,.1f}")
    print(f"Estimated spend:   HKD {total_gpu_minutes * args.rate:,.2f}")


if __name__ == "__main__":
    main()
