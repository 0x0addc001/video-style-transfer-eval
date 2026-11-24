# Evaluation Report Specification

The report must make the evidence behind each conclusion inspectable without
slowing the reader down. Use a **two-tier structure**: a short core body that a
reviewer can read in a few minutes, and an appendix that carries the full
definitions and per-case evidence. The section order below is fixed.

Generate Chinese and English variants from the same metrics and review export.
Translations must preserve section order, numbers, sample counts, method
identities, and limitations. Use manifest `label_zh` values for method names.
Never retranslate or silently alter technical metric names.

Every language variant must also have a standalone XeLaTeX source and a
standalone HTML report. The PDF is printed from the HTML (headless Chrome) so the
two stay visually identical.

## Core body

### 1. Header and traceability

Show, in this order:

- **Report ID** — timestamp plus the evidence hash prefix, e.g.
  `VST-20261124T112910-8c45376dabc9`;
- **Time** — generation timestamp, precise to the second;
- **Evidence** — path to the `metrics.json` that produced the report;
- **Benchmark / tool** — linked repository name with a GitHub icon; do not print
  the raw URL.

Do not print a claim-status badge, a claim sentence, or a dataset disclaimer in
the header.

### 2. Key results

One comparison table only:

- rows: evidence dimension (style, content, temporal, video quality, cost) and
  its headline metric;
- columns: **every tested method**, then nothing else — no verdict column and no
  configuration line above the table;
- best mean in bold with a light accent background; second best underlined and
  semi-bold; all values as mean ± standard deviation.

The table must let a reader compare methods left to right in one pass.

### 3. Evaluation configuration

A two-column table (`setting`, `value`) with the reproduction details:

- tested methods (display names);
- number of data items (clips);
- data source;
- seed;
- sampled frames per video;
- maximum evaluation side;
- temporal offsets;
- flow implementation.

Then a separate **metric classification** table: one row per family
(style, content, temporal, motion, video quality, cost) and the metric names in
that family. Do not repeat the family prefix inside the configuration table.

### 4. Quantitative results

One table per family, with the unit and preferred direction in the metric label
(e.g. `SSIM ↑ (dB)`). Mark best and second-best means, show `n`, and add one
`Comment` line under each table stating the comparison for its headline metric.
Show paired differences and confidence intervals once `n >= 5`.

### 5. Qualitative assessment (VLM)

Per-method scores for the five rubric dimensions, failure-tag counts, reviewer
count and model. This section is always called **Qualitative assessment (VLM)**;
do not use "blinded review" as the section name.

### 6. Discussion

Interpret style, content, motion and temporal stability, video quality and cost
separately, then state whether the evidence shows a trade-off.

### 7. Conclusion

Conclusion only. Do not add a separate recommendation section; fold any
recommendation into the conclusion when it follows directly from the evidence.

## Appendix

### A. Metric definitions and motivation

Formula, motivation, availability and interpretation caveat for every metric
shown or proposed for paper-grade evaluation. List unavailable metrics too,
marked as extensions.

### B. Dataset and pairing

Independent clip count, content and style identities, split, temporal offsets,
per-case pairing table, and which baselines were copied rather than rerun.

### C. Case study

Per case: source, style, every method's metrics, review result, contact sheet.
Flag cases whose ranking differs from the aggregate.

### D. Ablations and trade-offs

Controlled effects at matched style strength.

### E. Failure gallery

Representative artifacts with timestamp, method and evidence.

### F. Threats to validity

Content/style leakage, single-reference FID misuse, pixel metrics after
stylization, VLM bias, non-identical baselines, compression, flow-estimator
mismatch, sample size, stochasticity, VBench custom-input comparability, and the
static-clip bias of consistency metrics.

## Traceability rules

- The report ID must resolve to the evidence path and hash shown in the header.
- Synthetic or demo runs must state `example` as the data source.
- The same numbers must appear in Markdown, HTML, PDF and LaTeX.
