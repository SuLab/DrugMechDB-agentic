# Opus 4.8 vs Sonnet 4.6 — Curation Quality Evaluation

**Purpose:** decide which model to use for the production (forwardfill) curation run.
**Data:** `experiments/opus_vs_sonnet/` — 40 drug–disease pairs; Opus produced 40 outputs, Sonnet 35.
**Method:** three layers of signal —
1. **QC gate outcome + efficiency** from `experiments/opus_vs_sonnet/analysis.json` (full-pass, iters, cost, wall).
2. **Structural quality** from the repo's own deterministic scorer `scripts/quality/structural_quality.py` (net-polarity coherence, short-circuit, clinical-shortcut, type violations, cycles, duplicates — the mechanism-logic signals the QC gate does *not* catch).
3. **Evidence quality** parsed from the output YAMLs (items/edge, distinct refs, support-verdict purity, source tier).

Efficiency is from the subset where it was captured (Opus n=14, Sonnet n=25 of 40) — indicative, not complete.

---

## TL;DR / recommendation

**Use Opus 4.8 for production, plus a guide/prompt clarification + critic guard on shortcut/clinical edges.**

The QC gate and cost favor Opus decisively. Sonnet scores higher on the raw structural scorer, **but Opus's entire structural deficit is one systematic, root-caused, fixable behavior** — it appends a redundant `Drug —treats→ Disease` shortcut edge (a misapplication of a guide convention, §Root cause). Gate that and Opus leads on structure too, at lower cost, half the iterations, and better polarity coherence.

---

## Results

| Metric | Opus 4.8 | Sonnet 4.6 | Winner |
|---|---|---|---|
| **QC full-pass** | **40/40 (100%)** | 32/40 (80%) | Opus |
| Cost / pair *(partial capture)* | **$1.59** | $1.93 | Opus |
| Wall-clock / pair | **139 s** | 189 s | Opus |
| **Iterations to converge** | **16.8** | 34.7 (~2×) | Opus |
| Structural **HARD-clean** (no logic error) | 38% | **60%** | Sonnet |
| — matched head-to-head (35 shared pairs) | 31% | **60%** | Sonnet |
| Net-polarity **coherent** | **92%** (0 incoherent) | 86% (**2 incoherent**) | Opus |
| Evidence items / edge | 1.07 | **1.49** | Sonnet |
| Distinct refs / path | 3.5 | **4.7** | Sonnet |
| Support-verdict honesty | 100% SUPPORT | 95% + 12 PARTIAL | Sonnet |
| Full-text-tier usage | 3% | 1% | (both ~none) |
| Prefix-hygiene violations | 0 | 0 | tie |

**HARD-flag breakdown**
- Opus: `clinical_shortcut` 19 · `short_circuit` 10 · `type_violation` 6 · `net_polarity` 3
- Sonnet: `net_polarity` 5 · `clinical_shortcut` 6 · `type_violation` 4 · `short_circuit` 1

**Multi-path frequency:** records with >1 drug→disease route — Opus 28%, Sonnet 17%. A `treats`/clinical drug→disease shortcut edge — **Opus 19/40 (~48%)**, Sonnet 6/35 (~17%). "3-vs-4"-style subtle bypass (>1 path, all ≥3 edges, unequal length): **0** in either arm.

---

## Root cause of Opus's structural deficit (not hallucination — a guide misinterpretation)

Opus's HARD flags are dominated by `clinical_shortcut` (19) + `short_circuit` (10) — it appends a redundant `Drug —treats→ Disease` edge (or a drug→downstream edge) *on top of* the real mechanism chain. Example — Opus's Lisinopril → Hypertension record contained **both**:
- `Lisinopril —treats→ Hypertension` (1 edge), and
- `Lisinopril → ACE → Angiotensin II → AT1 receptor → vasoconstriction → Hypertension` (5 edges).

This is a misapplication of **CurationGuide.md §"Curating from GitHub Issues" (lines 331–334)**, which authorizes a single-link `Drug treats Disease` path **only** as a stub for indications with *no available mechanism*. Opus over-generalized it to always include the `treats` edge. The facts are true (the drug does treat the disease), so this is **over-generation from an ambiguous guide, not fabrication.** Sonnet made the same error ~3× less often.

The guide is genuinely ambiguous here: AGENTS.md line 22 only says to *drop* a redundant shortcut "if redundant" (cautious about removal, silent on creation), and `treats` is a fully sanctioned predicate.

---

## What the deterministic scorer catches vs. not

- **Catches (high precision):** `short_circuit` fires when a ≤2-edge route coexists with a ≥3-edge route; `clinical_shortcut` when a clinical-outcome edge goes drug→disease with >1 edge. Every Opus shortcut in this data was a ≤2-edge route → all caught.
- **Deliberate gap:** the `short_circuit` threshold is ≤2 by design, to avoid false-flagging *legitimate* reconverging branches (multi-target drugs, often 3–4 edges — e.g., Sonnet's four `(3,3)` records). A genuine "3-vs-4" bypass would slip past this rule; distinguishing a legit reconverging branch from a bogus 3-vs-4 bypass is a *semantic* judgment → deferred to the LLM critic / human review. (No such case occurred in these 75 records.)

So: deterministic structural checks are the internal-consistency floor; the LLM critic + human review remain necessary for biological correctness, evidence fit, and subtle bypasses.

---

## Recommendation (detail)

1. **Model:** Opus 4.8 — reliability (100% vs 80% QC), efficiency (~½ iterations, cheaper, faster), and polarity coherence all favor it at 4,846-record scale.
2. **Guide/prompt fix:** scope the stub explicitly — *the single-link "Drug treats Disease" path is only for indications with no available mechanism; when a mechanism exists, do not add a `treats` (or any drug→disease / drug→downstream) shortcut edge.*
3. **Guard:** wire `structural_quality.py`'s `clinical_shortcut` + `short_circuit` (+ `type_violation`) into the gate — bounce for a retry or strip the redundant edge (safe: redundant by definition). The semantic critic covers the subtle bypasses the rule can't.

---

## Caveats & next steps

- Cost/wall/iters captured on a partial subset (Opus 14, Sonnet 25 of 40); Opus produced 40 outputs, Sonnet 35 (the 5 missing are themselves a Sonnet reliability signal).
- Structural flags are the repo's heuristics — high-precision on HARD, but spot-check before acting on borderline records.
- **Next:** (a) re-curate ~10 of Opus's shortcut pairs with the clarified prompt and confirm the ~48% incidence collapses; (b) run the blinded LLM `judge/` for the subjective mechanism-plausibility axis; (c) capture cost on the full 40 for a true cost-per-good-path.
</content>
