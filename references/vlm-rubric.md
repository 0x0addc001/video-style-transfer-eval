# Blinded VLM Review Rubric

Use the generated contact sheets and, when available, the actual clips. Score each method independently while its label remains blinded. Do not infer the method from file order, metadata, or visual signature.

## Review Prompt

```text
You are evaluating video style transfer outputs. The source clip, style reference,
and anonymized candidate outputs are shown in the attached contact sheets. Assess
style adherence, content preservation, temporal stability, and artifact control.

Important:
- The style reference may have a different composition; judge the transferable
  palette, brushwork, texture, and visual language, not scene-copying.
- Use motion between consecutive sampled frames, not only the most attractive still.
- Compare candidates only when they share the same source and style.
- Cite frame indices or visible regions as evidence for every score.
- Do not assign a score if the evidence is insufficient. Set "insufficient": true.
- Return JSON only, matching the supplied schema.
```

## Ordinal Scores

Use integers from 1 to 5. A score of 3 is an acceptable midpoint, not a default.

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| `style_adherence` | Style is absent or unrelated | Recognizable transfer, inconsistent across regions or time | Coherent transfer of palette, texture/brushwork, and visual language |
| `content_preservation` | Source identity or scene structure is lost | Main content is recognizable but local identity/structure changes are visible | Identity, layout, object boundaries, and semantics remain clear |
| `temporal_stability` | Severe flicker, warping, or motion discontinuity | Localized flicker/drift or minor motion disagreement | Stable through sampled motion with no material temporal artifact |
| `artifact_control` | Obvious melting, ghosting, holes, duplication, or texture sticking | Noticeable but localized artifacts | No material artifacts at the reviewed scale |
| `overall_visual_quality` | Not usable | Usable with visible compromises | Polished and plausible for the intended use |

Confidence is `low`, `medium`, or `high`. Low-confidence scores require a reason.

## Failure Tags

Use only relevant tags:

`flicker`, `texture_sticking`, `texture_drift`, `identity_drift`, `geometry_melting`, `edge_ghosting`, `occlusion_break`, `new_region_error`, `motion_duplication`, `temporal_jump`, `color_bleed`, `banding`, `detail_loss`, `reference_copied`.

## Pairwise Preference

After independent scores, choose a winner for each case and dimension:

```json
{
  "dimension": "content_preservation",
  "winner": "M1",
  "tie": false,
  "confidence": "medium",
  "evidence": "Frame 24: M2 bends the foreground edge during occlusion."
}
```

Preference is often more reliable than ordinal scores. Preserve the evidence and report order effects or disagreement if more than one reviewer is used.

## Review JSON Schema

```json
{
  "schema_version": "1.0",
  "reviewer": {
    "id": "reviewer-1",
    "type": "vlm",
    "model": "model-name-version",
    "review_date": "2026-11-08",
    "blind": true,
    "input_scope": "contact_sheets_only"
  },
  "scores": [
    {
      "case_id": "case_001",
      "method_blind_id": "M1",
      "insufficient": false,
      "style_adherence": 4,
      "content_preservation": 5,
      "temporal_stability": 3,
      "artifact_control": 3,
      "overall_visual_quality": 4,
      "confidence": "medium",
      "failure_tags": ["texture_sticking"],
      "evidence": "Frames 12-24: texture remains attached but edge detail drifts near the occluding hand.",
      "comments": ""
    }
  ],
  "preferences": [
    {
      "case_id": "case_001",
      "dimension": "temporal_stability",
      "winner_blind_id": "M1",
      "tie": false,
      "confidence": "medium",
      "evidence": "M1 changes less across the sampled motion sequence."
    }
  ]
}
```

Do not add unrequested composite scores. Report tooling computes descriptive averages and preference counts but leaves dimensions separate.
