#!/usr/bin/env python3
"""Compute CSD style/content consistency for generated videos.

CSD (contrastive style descriptor) is the CLIP ViT-L/14 backbone with separate
style and content heads introduced by "Measuring Style Similarity in Diffusion
Models" (Somepalli et al., arXiv:2404.01292). EchoStyle (ECCV 2026) reports the
style-head variant between the first and every later frame as "Style Consis.".

This script is the GPU-side adapter: it emits a schema 1.0 evidence file that
`merge_metrics.py` merges into the diagnostic run. It never runs on the CPU-only
laptop unless you accept very slow inference.

Example (on the GPU host, after the videos are copied back):

    python scripts/csd_consistency.py \
      --manifest evaluation/manifest.json \
      --output evaluation/evidence/csd.json \
      --checkpoint yuxi-liu-wired/CSD \
      --device cuda

Requires: torch, openai-clip (`pip install git+https://github.com/openai/CLIP.git`),
transformers, huggingface_hub, and OpenCV for frame decoding.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import numpy as np

from evidence_io import (
    iter_case_outputs,
    load_manifest,
    select_frame_indices,
    write_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Evidence JSON to write for merge_metrics.py.",
    )
    parser.add_argument(
        "--checkpoint",
        default="yuxi-liu-wired/CSD",
        help="Hugging Face repo id or local directory with the CSD weights.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Inference device. 'auto' prefers CUDA and falls back to CPU.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=32,
        help="Evenly spaced frames sampled per video (first frame always included).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Frames per forward pass.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process the first N manifest outputs (debugging).",
    )
    return parser.parse_args()


def select_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def read_frames(video_path: Path, max_frames: int) -> list[Any]:
    """Decode evenly spaced RGB frames as PIL images."""
    import cv2
    from PIL import Image

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    indices = select_frame_indices(frame_count, max_frames)
    if not indices:
        capture.release()
        raise ValueError(f"Video reports no decodable frames: {video_path}")
    wanted = set(indices)
    frames: dict[int, Any] = {}
    index = 0
    last = indices[-1]
    while index <= last:
        ok, frame = capture.read()
        if not ok:
            break
        if index in wanted:
            frames[index] = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        index += 1
    capture.release()
    return [frames[i] for i in sorted(frames)]


def cosine_first_frame(embeddings: np.ndarray) -> float | None:
    """Mean cosine similarity between the first row and every later row."""
    if embeddings.ndim != 2 or embeddings.shape[0] < 2:
        return None
    first = embeddings[0]
    rest = embeddings[1:]
    first_norm = float(np.linalg.norm(first))
    rest_norms = np.linalg.norm(rest, axis=1)
    denominator = first_norm * rest_norms
    valid = denominator > 1e-12
    if not np.any(valid):
        return None
    scores = (rest[valid] @ first) / denominator[valid]
    return float(np.mean(scores))


def sequence_metrics(style_embeddings: np.ndarray, content_embeddings: np.ndarray) -> dict[str, float]:
    """CSD-S/CSD-C metrics for one clip, omitting metrics it cannot support."""
    metrics: dict[str, float] = {}
    style_score = cosine_first_frame(style_embeddings)
    content_score = cosine_first_frame(content_embeddings)
    if style_score is not None:
        metrics["csd_s"] = round(style_score, 6)
    if content_score is not None:
        metrics["csd_c"] = round(content_score, 6)
    return metrics


def load_encoder(checkpoint: str, device: str) -> Any:
    """Build the CSD CLIP encoder, importing torch/clip lazily."""
    try:
        import clip
        import torch
        import torch.nn as nn
        from huggingface_hub import PyTorchModelHubMixin
        from transformers import CLIPProcessor, PretrainedConfig
    except ImportError as error:  # pragma: no cover - optional dependency path
        raise RuntimeError(
            "CSD scoring requires torch, openai-clip, transformers and "
            "huggingface_hub. On the GPU host run:\n"
            "  pip install torch transformers huggingface_hub\n"
            "  pip install git+https://github.com/openai/CLIP.git\n"
            f"Original import error: {error}"
        ) from error

    class CSDCLIPConfig(PretrainedConfig):
        model_type = "csd_clip"

        def __init__(
            self,
            name: str = "csd_large",
            embedding_dim: int = 1024,
            feature_dim: int = 1024,
            content_dim: int = 768,
            style_dim: int = 768,
            content_proj_head: str = "default",
            **kwargs: Any,
        ) -> None:
            super().__init__(**kwargs)
            self.name = name
            self.embedding_dim = embedding_dim
            self.feature_dim = feature_dim
            self.content_dim = content_dim
            self.style_dim = style_dim
            self.content_proj_head = content_proj_head
            self.task_specific_params = None

    class CSDCLIP(nn.Module, PyTorchModelHubMixin):
        """CLIP visual backbone plus the two disentangled projection heads."""

        def __init__(
            self,
            name: str = "vit_large",
            content_proj_head: str = "default",
            **kwargs: Any,
        ) -> None:
            super().__init__()
            self.content_proj_head = content_proj_head
            if name == "vit_large":
                clipmodel, _ = clip.load("ViT-L/14")
                self.backbone = clipmodel.visual
                self.embedding_dim = 1024
                self.feature_dim = 1024
                self.content_dim = 768
                self.style_dim = 768
                self.name = "csd_large"
            elif name == "vit_base":
                clipmodel, _ = clip.load("ViT-B/16")
                self.backbone = clipmodel.visual
                self.embedding_dim = 768
                self.feature_dim = 512
                self.content_dim = 512
                self.style_dim = 512
                self.name = "csd_base"
            else:
                raise ValueError(f"Unsupported CSD backbone: {name}")
            self.last_layer_style = copy.deepcopy(self.backbone.proj)
            self.last_layer_content = copy.deepcopy(self.backbone.proj)
            self.backbone.proj = None
            self.config = CSDCLIPConfig(
                name=self.name,
                embedding_dim=self.embedding_dim,
                feature_dim=self.feature_dim,
                content_dim=self.content_dim,
                style_dim=self.style_dim,
                content_proj_head=self.content_proj_head,
            )

        def get_config(self) -> dict[str, Any]:
            return self.config.to_dict()

        @property
        def dtype(self) -> Any:
            return self.backbone.conv1.weight.dtype

        @property
        def device(self) -> Any:
            return next(self.parameters()).device

        def forward(self, pixel_values: Any) -> tuple[Any, Any, Any]:
            feature = self.backbone(pixel_values)
            style = nn.functional.normalize(
                feature @ self.last_layer_style, dim=1, p=2
            )
            content = nn.functional.normalize(
                feature @ self.last_layer_content, dim=1, p=2
            )
            return feature, content, style

    try:
        model = CSDCLIP.from_pretrained(checkpoint)
    except Exception as error:  # pragma: no cover - network/checkpoint specific
        raise RuntimeError(
            f"Cannot load CSD weights from '{checkpoint}'. Check the repo id, "
            f"your network access to the Hugging Face Hub, and the model files. "
            f"Original error: {error}"
        ) from error
    model = model.to(device).eval()
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")

    class Encoder:
        def encode(self, images: list[Any], batch_size: int) -> tuple[np.ndarray, np.ndarray]:
            style_batches = []
            content_batches = []
            for start in range(0, len(images), batch_size):
                batch = images[start : start + batch_size]
                inputs = processor(images=batch, return_tensors="pt")
                pixel_values = inputs["pixel_values"].to(device).to(model.dtype)
                with torch.no_grad():
                    _, content, style = model(pixel_values)
                style_batches.append(style.float().cpu().numpy())
                content_batches.append(content.float().cpu().numpy())
            return (
                np.concatenate(style_batches, axis=0),
                np.concatenate(content_batches, axis=0),
            )

    return Encoder()


def main() -> int:
    args = parse_args()
    manifest, manifest_dir = load_manifest(args.manifest)
    device = select_device(args.device)
    encoder = load_encoder(args.checkpoint, device)

    evidence_cases: list[dict[str, Any]] = []
    skipped = 0
    for index, (case_id, method_id, video_path) in enumerate(
        iter_case_outputs(manifest, manifest_dir)
    ):
        if args.limit and len(evidence_cases) >= args.limit:
            break
        if not video_path.is_file():
            print(f"[skip] missing video for {case_id}/{method_id}: {video_path}")
            skipped += 1
            continue
        frames = read_frames(video_path, args.max_frames)
        if len(frames) < 2:
            print(f"[skip] fewer than two decodable frames: {video_path}")
            skipped += 1
            continue
        style_embeddings, content_embeddings = encoder.encode(frames, args.batch_size)
        metrics = sequence_metrics(style_embeddings, content_embeddings)
        if not metrics:
            print(f"[skip] no CSD metric could be computed: {video_path}")
            skipped += 1
            continue
        evidence_cases.append(
            {"case_id": case_id, "method_id": method_id, "metrics": metrics}
        )
        print(
            f"[{index + 1}] {case_id}/{method_id}: "
            + ", ".join(f"{key}={value:.4f}" for key, value in metrics.items())
        )

    if not evidence_cases:
        print("No CSD evidence was produced.", file=sys.stderr)
        return 1

    implementation = {
        "name": "CSD contrastive style descriptor (CLIP ViT-L/14, two projection heads)",
        "version_or_commit": f"{args.checkpoint} @ openai/clip-vit-large-patch14",
        "device": device,
        "resolution": "CLIP 224x224 center crop",
        "notes": (
            "CSD-S compares every later frame with the first frame of the same "
            "clip; CSD-C uses the content head of the same model. Frames are "
            "evenly sampled and identical preprocessing is required for every "
            "compared method."
        ),
    }
    write_evidence(args.output, evidence_cases, implementation)
    print(
        f"Wrote {len(evidence_cases)} CSD case records "
        f"({skipped} skipped) to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
