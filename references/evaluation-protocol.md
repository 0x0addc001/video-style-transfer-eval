# Video Style Transfer Evaluation Protocol

## Objective

Answer four separate questions:

1. Does the output adopt the reference style without merely copying its composition?
2. Does the output preserve source identity, structure, and semantics?
3. Does it preserve source motion and remain stable through time?
4. What quality does it achieve for the runtime and memory cost?

The course brief requires style quality, content preservation, and temporal stability. The supplied evaluation notes additionally recommend ArtFID, FID, CLIP-I, SSIM, LPIPS, CLIP-F, warping error, EPE, tLP, CLIP-CONS, effect size in the temporal dimension, and ablations at matched style strength. This skill operationalizes those dimensions in evidence tiers.

## Experimental Design

- Use 3-5 second source clips and a fixed frame-sampling plan across methods.
- Pair every comparison on the same source clip and style image.
- Hold out content and style combinations. Do not select intervention layers and report performance on the same pairs.
- Use multiple contents and styles. A single visually strong example is a qualitative illustration, not evidence of generalization.
- Run each stochastic method under a recorded seed. Report per-case means first, then macro means and confidence intervals.
- For ablations, vary one factor while holding inference resolution, schedule, seed, and evaluation implementation fixed.
- When comparing content or motion preservation, compare at similar achieved style strength. Plot the style-preservation trade-off rather than selecting the single best-looking operating point.
- Include a source-replay or identity-transform control when diagnosing temporal metrics. It establishes the best attainable content/motion agreement and exposes compression effects.

## Evidence Tiers

### Tier 1: Deterministic Diagnostics

Run `scripts/evaluate.py` for all cases.

| Dimension | Metric | Interpretation |
|---|---|---|
| Content | PSNR | Global pixel agreement; sensitive to colorization and compression. |
| Content | SSIM | Luminance, contrast, and local structure agreement. |
| Style | LAB palette W1 | Long-tail lower-is-better palette distance; weak proxy for style. |
| Motion | Flow EPE | Endpoint difference between source and output optical flow. |
| Motion | Flow correlation | Agreement in motion direction; less sensitive than EPE to magnitude. |
| Temporal | Warping RMSE/MAE | Error after output frames are warped with source flow and occlusion is masked. |
| Temporal | Luminance flicker | Standard deviation of frame mean luminance after removing a linear trend. |
| Operational | Runtime, peak memory | Report from the same hardware and settings as the compared run. |

The script uses OpenCV Farneback flow by default. It is deterministic and useful for ranking within the same run, but it is not RAFT and must not be presented as the UniVST/paper implementation.

### Tier 2: Paper-Grade Perceptual Metrics

Choose metrics that support the claim you are making:

| Claim | Preferred evidence |
|---|---|
| Global style match | CLIP-I, VGG Gram/style features, reference-style distribution FID |
| Preserve appearance and semantics | LPIPS, CLIP-F |
| Joint content/style | ArtFID |
| Motion preservation | EPE from RAFT or another fixed flow estimator |
| Temporal texture stability | Source-flow warping RMSE, tLP |
| Semantic temporal stability | CLIP-CONS |
| Style-preservation frontier | Paired curves over intervention strength at matched style |

Use one fixed implementation and preprocessing pipeline for all methods. Store versioned metric outputs as evidence files and merge them into the evaluation run. Separately list baseline values copied from another paper; they are not a unified rerun.

External values can be merged into the diagnostic run with:

```bash
python video-style-transfer-eval/scripts/merge_metrics.py \
  --metrics evaluation_run/metrics.json \
  --evidence metrics/lpips_clip.json \
  --output evaluation_run/metrics_merged.json
```

See [assets/advanced-metrics.example.json](../assets/advanced-metrics.example.json) for the minimal evidence schema. Record the implementation name, version/commit, hardware, resolution, and preprocessing in `metric_implementation`.

## Metric Definitions and Caveats

- **CLIP-I:** cosine similarity of CLIP image embeddings for a generated frame and the style image. Content mismatch can dominate the embedding, so use it comparatively and supplement with a style-specific encoder or VLM review.
- **CLIP-F:** cosine similarity of CLIP image embeddings for generated and source frames. It measures semantic content, not geometric fidelity.
- **LPIPS:** normalized deep-feature distance. Prefer it over raw PSNR/SSIM for perceptual preservation, but do not use it alone.
- **FID:** Frechet distance between feature distributions. It requires enough outputs and independent style references to estimate distributions; a single style image is not a valid style distribution.
- **ArtFID:** combines content and style closeness. Follow the cited implementation; changing LPIPS or inception preprocessing breaks comparability.
- **Warping error:** estimate flow on the original sequence, warp temporally adjacent generated frames into alignment, and exclude occluded or invalid pixels. Use the same offsets for every method.
- **EPE:** compare source and generated optical flow at identical coordinates. A very different flow estimator or no occlusion handling can produce misleading large errors.
- **tLP:** LPIPS applied after source-flow warping; use a fixed temporal offset and report it.
- **CLIP-CONS:** compare the semantic change vector between adjacent source and generated frames. This tests semantic change agreement, not pixel stability.

## Statistical Reporting

For each method and metric, report:

- number of valid clips `n`;
- per-case values;
- macro mean;
- standard deviation or median and IQR;
- paired mean difference against the primary baseline;
- 95% bootstrap confidence interval for the paired difference when `n >= 5`.

Use macro averages so a long clip does not dominate. Report all temporal offsets. Do not present a confidence interval from repeated frames as independent samples; the clip is the sampling unit.

## Ablations

At minimum, evaluate:

- shallow, middle, and deep intervention locations;
- denoising interval and intervention strength;
- direct blending, full-channel AdaIN, and subspace AdaIN;
- subspace rank and extraction strategy;
- shared versus per-frame statistics;
- attention anchoring on/off.

For each ablation, show style strength and at least one preservation metric. Include a style-preservation plot and identify operating points with a similar style score.

## Failure Analysis

Review flicker, texture sticking, drift at motion boundaries, occlusion failure, newly revealed regions, identity changes, geometric distortion, and temporal discontinuity. Record a timestamp and contact sheet for each failure. Do not hide failures through cherry-picked stills.
