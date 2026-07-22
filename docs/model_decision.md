# Production curation-model decision

> **Decision:** the production curation model is **Claude Opus 4.8** (`claude-opus-4-8`),
> paired with the shortcut-edge guardrail. Recorded here as the single source of truth.
> **Status:** decided on the reliability + cost + structural evidence below; the blinded
> LLM-judge pass (#8) and human plausibility review (#12) are the remaining *confirmation*
> gates and are cross-referenced, not blockers to recording this choice.

## Evidence

A two-arm, blinded, isolated curation eval over **40 drug–disease pairs** compared Opus 4.8
against Sonnet 4.6 under byte-identical framing (only the model id differed). Raw run data is
committed under `experiments/opus_vs_sonnet/` (`opus/run_summary.json`, `sonnet/run_summary.json`,
`analysis.json`, and every produced path YAML); the detailed write-up is
`docs/opus_vs_sonnet_quality.md`.

| Metric | Opus 4.8 | Sonnet 4.6 | Winner |
|---|---|---|---|
| QC full-pass (all 4 layers) | **40/40 (100%)** | 32/40 (80%) | **Opus** |
| Cost / pair *(partial capture)* | **$1.59** | $1.93 | **Opus** |
| Wall-clock / pair | **139 s** | 189 s | **Opus** |
| Iterations to converge | **16.8** | 34.7 (~2×) | **Opus** |
| Net-polarity coherent | **92%** | 86% | **Opus** |
| Structural HARD-clean (raw) | 38% | **60%** | Sonnet |

## Why Opus, despite the raw structural-cleanliness gap

Opus's *entire* structural deficit is **one systematic, root-caused, deterministically-fixable
behavior**: it appends a redundant `Drug —treats→ Disease` shortcut edge *on top of* the real
mechanism chain (`clinical_shortcut` ×19, `short_circuit` ×10 across the arm). This is an
over-generalization of a `CurationGuide.md` convention that authorizes a single-link
`Drug treats Disease` path **only** as a stub when no mechanism is available — the facts are true,
so it is over-generation, **not fabrication**. It is exactly what the deterministic structural gate
catches: every such shortcut in the eval was a ≤2-edge route and was flagged.

Gate that one behavior and Opus leads on structure too — at lower cost, ~half the iterations, faster
wall-clock, and better net-polarity coherence, which is decisive at 4,846-record scale.

## Required guardrails (part of this decision)

1. **Shortcut-edge guard** — the anti-shortcut-edge harness + guide clarification (issue #1, closed)
   and the deterministic structural gate that HARD-blocks `clinical_shortcut` / `short_circuit` /
   `direct_drug_disease` (issue #7).
2. **Semantic critic + human review** remain necessary for biological correctness, evidence fit,
   and subtle bypasses the deterministic checks defer (see `docs/path_quality_framework.md` §6–§8).

## Confirmation gate (not yet cleared)

The blinded LLM-judge comparison (#8) and the human plausibility review (#12) will confirm this
choice against subjective quality; until their agreement clears calibration they *propose*, humans
*dispose* (`docs/path_quality_framework.md` §7). This decision is revisited if either contradicts
the evidence above.

### See also
- `docs/opus_vs_sonnet_quality.md` — full eval analysis.
- `docs/path_quality_framework.md` — the quality framework the confirmation gate operationalizes.
- Issues #1 (shortcut guard, closed), #7 (structural gate), #8 (blinded judge), #12 (human review).
