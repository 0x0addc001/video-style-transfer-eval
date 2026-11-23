# Evaluating EchoStyle with this skill

**Languages:** English | [简体中文](echostyle-evaluation-plan.zh-CN.md)

A runbook for using `video-style-transfer-eval` on [EchoStyle](https://github.com/HKUST-C4G/EchoStyle)
(ECCV 2026, arXiv:2606.25465) and, optionally, on the baselines it reports.

## Decision: where each step runs

EchoStyle's own README requires **8× NVIDIA GPUs with 80 GB each** for inference
(14B Wan2.2 DiT with FSDP/Ulysses; the lightning checkpoints are faster but still
CUDA-only). The laptop cannot run inference, and the heavy external metrics are
also GPU-shaped. So the practical split is:

| Step | Runs on | Why |
|---|---|---|
| Manifest authoring, clip/style curation | laptop | pure JSON + file layout |
| EchoStyle inference, baselines | GPU server | 8×80 GB CUDA, flash-attn, Wan2.2 weights |
| `scripts/evaluate.py` diagnostics | laptop | OpenCV Farneback; CPU is fine, deterministic |
| Blind contact-sheet review | laptop | visual review of small JPEGs |
| VBench (`custom_input`) | GPU server | AMT/MUSIQ/DINO/CLIP models; CPU would take hours per run |
| `scripts/csd_consistency.py` | GPU server (CPU possible but slow) | CLIP ViT-L/14 over thousands of frames |
| `merge_metrics.py`, `validate_review.py`, `render_report.py` | laptop | JSON + ReportLab; no CUDA |

## Data you need

1. **Source clips** — 3–5 seconds each; every method must use the *same* clip so
   comparisons stay paired.
2. **Style condition** — EchoStyle is text-driven (Chinese style prompts), but the
   skill's LAB palette metric needs a `style_image`. The cheap approach: one
   representative image per style, used as a palette anchor, and say so in the
   report ("palette anchor, not an EchoStyle input").
3. **Outputs and cost** — one MP4 per method per case plus runtime and peak memory.

You do **not** need the VBench prompt suite (skipped in `custom_input` mode) or a
FID reference distribution unless you actually compute FID.

Scale: EchoStyle evaluates 50 video-instruction pairs over nine styles. This skill
needs at least two pairs for a Comparative claim, and fewer than five clips leaves
the paired intervals unstable.

Sources, in order of preference: EchoStyle's bundled `assets/videos/01–11.mp4`
for a smoke test; self-recorded or public footage (DAVIS, Videvo, Pexels — check
licences and consent) for the real run; **never** V-Style20k, which is EchoStyle's
training data and would leak.

Transfer only three things back from the server: the generated MP4s, the VBench
result JSONs, and the CSD evidence JSON. Everything else stays local.

## Step 1 — Manifest (laptop)

Mirror EchoStyle's evaluation set: 50 video-instruction pairs over nine styles
(Ghibli, anime, ink wash, oil painting, ukiyo-e, Disney 3D, and so on). Pair every
method on the same source clip. Start from
[assets/manifest.example.json](../assets/manifest.example.json).

Record on the server side and copy into the manifest/report:

- EchoStyle commit and LoRA checkpoint ids;
- seed, `--size` (their default is `1280*720`), `--sample_steps`, guidance scale;
- whether standard (50 steps) or lightning (10 steps) mode was used;
- GPU model, node count, peak memory, wall-clock runtime per clip.

Do not compare a lightning run with a standard run as if they were one method.

## Step 2 — Inference (server)

Follow the EchoStyle README: conda env with Python ≥ 3.10, torch ≥ 2.4 (cu121),
flash-attn, then `bash scripts/eval.sh`. Keep one output directory per method:

```text
evaluation/
  data/source/case_001.mp4
  data/style/style_01.jpg
  outputs/echostyle/case_001.mp4
  outputs/vace_flow/case_001.mp4
```

Write `outputs/<method>/<case_id>.mp4` with the exact case IDs used in the
manifest; the adapters match results by path and filename.

## Step 3 — External metrics (server)

VBench, `custom_input` mode, one run per method (same commit for all methods):

```bash
vbench evaluate --videos_path evaluation/outputs/echostyle \
  --dimension motion_smoothness --mode=custom_input
vbench evaluate --videos_path evaluation/outputs/echostyle \
  --dimension imaging_quality --mode=custom_input
# repeat for aesthetic_quality, subject_consistency, background_consistency,
# temporal_flickering, dynamic_degree
```

Then import the per-video JSONs:

```bash
python scripts/vbench_import.py \
  --manifest evaluation/manifest.json \
  --results evaluation/vbench_results \
  --output evaluation/evidence/vbench.json
```

CSD style/content consistency (this is the `Style Consis.` column in EchoStyle's
Table 1):

```bash
pip install torch transformers huggingface_hub
pip install git+https://github.com/openai/CLIP.git

python scripts/csd_consistency.py \
  --manifest evaluation/manifest.json \
  --output evaluation/evidence/csd.json \
  --checkpoint yuxi-liu-wired/CSD \
  --device cuda \
  --max-frames 32
```

Use the same `--max-frames` for every method. EchoStyle compares each later frame
with the first frame of the clip; the adapter does the same.

## Step 4 — Diagnostics and review (laptop)

```bash
python scripts/evaluate.py --manifest evaluation/manifest.json \
  --output-dir evaluation_run --blind

python scripts/validate_review.py \
  --review reviews/*.json \
  --blind-map evaluation_run/review_packet/blind_map.json
```

Score the contact sheets with [references/vlm-rubric.md](../references/vlm-rubric.md)
before opening `blind_map.json`.

## Step 5 — Merge and render (laptop)

```bash
python scripts/merge_metrics.py \
  --metrics evaluation_run/metrics.json \
  --evidence evaluation/evidence/csd.json evaluation/evidence/vbench.json \
  --output evaluation_run/metrics_merged.json

python scripts/render_report.py \
  --metrics evaluation_run/metrics_merged.json \
  --review evaluation_run/review_packet/validated_reviews.json \
  --output-dir evaluation_report \
  --language both \
  --primary echostyle \
  --baseline <baseline_id>
```

The report then contains a dedicated **Video quality** table for the VBench
dimensions, CSD-S/CSD-C in the style and content tables, and a definition with
formula, motivation, and caveat for every one of them.

## How this maps to EchoStyle's Table 1

| EchoStyle column | This skill | Note |
|---|---|---|
| Style Similarity | `csd_s` (or blinded review) | EchoStyle uses Gemini-3-pro pairwise win rates; that needs an API key and is not reproduced here. CSD-S is the reproducible part. |
| Style Consis. | `csd_s` | same CSD model family, frame-vs-first-frame |
| Motion Smooth. | `vbench_motion_smoothness` | VBench dimension |
| Imaging Qual. | `vbench_imaging_quality` | VBench (MUSIQ) |
| Static Qual. | `vbench_subject_consistency` + `vbench_background_consistency` | closest VBench analogues; label them as such, not as Gemini scores |
| Dynamic Qual. | `vbench_dynamic_degree` | bounded by source motion; compare like with like |
| Aesthetic Qual. | `vbench_aesthetic_quality` | biased toward photographic aesthetics |
| Human preference | blinded VLM/human rubric + validated reviews | keep style, content, and temporal dimensions separate |

Do not present a `Gemini-3-pro` column as if it were reproduced by this skill.
Either run the same model with the same prompt and record it, or mark the column
as "baseline values copied from the paper" in the report.

## Practical notes

- **Resolution mismatch.** EchoStyle outputs 1280×720. If sources differ, the
  diagnostic SSIM/PSNR and flow metrics degrade for reasons unrelated to the
  method. Resize to a common evaluation resolution and say so in the report.
- **Cost of VBench on CPU.** Do not try it on the laptop for 50 clips; the AMT
  and MUSIQ passes alone are many hours. Run it on the server.
- **CSD is cheap but not free.** 50 clips × 32 frames at ViT-L/14 is roughly
  1,600 forwards; with a batch of 8 on one A100 it is a few minutes, on CPU it is
  tens of minutes.
- **Keep the same frame count** between methods in VBench and CSD. VBench
  averages over decoded frames, so a longer clip can dominate a dimension.
- **Statistical unit is the clip.** With 50 clips you can report bootstrap
  confidence intervals; with fewer than five, label results exploratory.
- **Long videos.** EchoStyle supports sliding-window long-video inference. If a
  clip is longer than the evaluation budget, evaluate the same time window for
  every method rather than letting clip length differ.

## Budget and smoke test

SuperPOD bills **HKD 0.2 per GPU-minute (HKD 12 per GPU-hour)**; each student gets
**HKD 2,000**, i.e. about **167 GPU-hours ≈ 21 hours on a full 8-GPU node**.

| Stage | Usage | Estimate |
|---|---|---|
| Local smoke (demo clips, diagnostics only) | 0 GPU | HKD 0 |
| Server smoke: 1 clip on 8 GPUs, ~10 min | 80 GPU-min | ≈ HKD 16 |
| VBench + CSD for 50 clips, 1 GPU | 1–2 GPU-h | ≈ HKD 12–24 |
| Full 50 clips at 2.5 min each | ~1000 GPU-min | ≈ HKD 200 |
| Full 50 clips at 6 min each | ~2400 GPU-min | ≈ HKD 480 |

Measure one clip before committing to the full set. The credit covers roughly
4–10 complete evaluations, and rerunning a preempted job is billed again.

To let an agent drive the cluster non-interactively, install this Mac's public key
once (`ssh-copy-id -i ~/.ssh/id_ed25519.pub <user>@superpod.ust.hk`, needs a
password and Duo), then key-based `ssh` commands need no MFA.
