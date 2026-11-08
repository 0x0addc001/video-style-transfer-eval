# Evaluation Report Specification

The report must make the evidence behind each conclusion inspectable. Use the following sections in order.

Generate Chinese and English variants from the same metrics and review export. The translations must preserve section order, numbers, sample counts, evidence gates, method identities, and limitations. Use manifest `label_zh` values for method names when Chinese wording would otherwise remain ambiguous; never retranslate or silently alter technical metric names.

Every language variant must also have a standalone XeLaTeX source. Use `booktabs` rules, captions above tables, units and preferred directions, mean and dispersion, best/second-best marking, and appendix-level per-case evidence. Keep tables copyable into a CVPR-style paper; avoid dashboard-only visual encodings that disappear in print.

## 1. Header and Claim Status

Include project, run name, date, evaluator, schema version, split, and one status:

- `Exploratory`: synthetic or development-only evidence.
- `Provisional`: diagnostic metrics complete, visual review or paper-grade metrics incomplete.
- `Comparative`: paired held-out evidence and appropriate uncertainty are present.
- `Paper-ready`: all required evidence for the stated claim is present and traceable.

State the claim in one sentence. Do not write "Method A is better" without naming the dimension, dataset, and comparison.

## 2. Executive Verdict

Provide 3-5 findings:

- observed advantage or regression;
- evidence size and uncertainty;
- strongest failure mode;
- cost implication;
- recommended next experiment.

Never create an overall scalar score when the dimensions disagree. A recommendation may be conditional on the intended use.

## 3. Protocol and Reproducibility

List manifest path/hash, method seed, checkpoint or commit, inference resolution, sampling plan, hardware, runtime, peak memory, metric implementations, reviewer model/version, frame sampling, and missing data.

## 4. Dataset and Pairing

State number of independent clips, content identities, styles, split, temporal offsets, and maximum sampled frames. Confirm every compared method was paired. Identify external baselines whose numbers were copied rather than rerun.

## 5. Quantitative Results

Separate tables:

- style;
- content;
- temporal/motion;
- cost.

Use arrows to show preferred direction. Show `n`, mean, dispersion, and missing cases. For comparisons, show paired difference and confidence interval once `n >= 5`.

For paper-facing tables, mark the best and second-best means, explain the marking in the caption, and distinguish a direction-adjusted paired difference from the raw metric difference. Report standardized paired effect size only as descriptive evidence when the sample is small.

Before the quantitative results, include a metric-definition section with the formula, motivation, current-run availability, and interpretation/reporting caveat for every metric shown or proposed for paper-grade evaluation. This includes SSIM, PSNR, LPIPS, CLIP-F, CLIP-I, FID, ArtFID, LAB palette distance, warping error, EPE, flow correlation, tLP, CLIP-CONS, luminance flicker, VLM aggregation, and runtime/peak-memory cost. Do not hide unavailable metrics; mark them as extensions while retaining their definitions.

## 6. Blinded Visual Review

Report reviewer identity/model, blinding, input type, and agreement across reviewers. Keep the five dimensions separate. Show failure-tag counts and pairwise preferences with supporting frame ranges. Label contact sheets as evidence, not ground truth.

## 7. Per-Case Outcomes

For each case, show source, style, methods, metrics, and review result. Flag cases where models rank differently from aggregate trends. Do not drop inconvenient cases without a documented validity failure.

## 8. Ablations and Trade-offs

Present controlled effects, not just the best configuration. Use style strength on one axis and preservation/motion on the other. Identify matched-style comparisons.

## 9. Failure Gallery

Include at least one representative artifact against the intended reason. Give timestamp/frame, method, and evidence. If no failure was found, state the sampled scope; do not imply universal robustness.

## 10. Threats to Validity

At minimum discuss content/style leakage, single-reference FID misuse, pixel metrics after stylization, VLM position bias, non-identical baseline settings, compression, flow-estimator mismatch, small sample size, and stochasticity.

## 11. Conclusion and Recommendation

Repeat only claims supported by the earlier tables. Distinguish observed evidence, practical recommendation, and unverified hypothesis.

The conclusion must state whether any method dominates across style, content, motion, and cost. If dimensions disagree, report a trade-off and avoid a universal superiority claim. Explicitly identify when the sample size does not support stable confidence intervals.

## Evidence Gates

Apply these gates in the report:

- `Comparative` requires paired held-out methods and at least two independent source/style pairs.
- A quantitative ranking over multiple clips should include uncertainty.
- A style-preservation claim requires matched style strength or an explicit confound.
- A paper-grade claim requires named, fixed implementations for perceptual metrics.
- VLM statements require blinded review records; otherwise label them author observations.
- Failures require a linked contact sheet or clip with timestamps.
- Synthetic/demo values must be labeled prominently and never presented as model benchmark results.
