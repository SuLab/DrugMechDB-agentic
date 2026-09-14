# Shortcut-edge fix — re-curation validation

**Result: the combined shortcut-flag rate dropped from 100% to 0% on a 14-pair re-curation set.**
Target (≤10%) met. This is the empirical validation of the "one connected chain / no shortcut
edge" prompt-and-guide fix.

## What was being fixed

The curation guide authorized a single-link `Drug —treats→ Disease` path, but only as a *stub* for
indications with no findable mechanism. The curation agent over-applied it: on ~half its records it
appended a redundant `Drug —treats→ Disease` (or drug→downstream) **shortcut edge on top of a
fully-worked mechanism**. Those edges restate the conclusion the chain already expresses and are HARD
errors in the deterministic structural checks (`clinical_shortcut`, `short_circuit`).

The fix makes the rule unambiguous in the curation prompt and guide, and adds shortcut detection to
the semantic reviewer:

- `AGENTS.md` §0 (authoritative contract, also the system prompt the curation harness feeds the
  agent) — a numbered "one connected chain, no shortcut/bypass edge" rule + a before/after
  anti-pattern in §8.
- `.claude/commands/curate.md` — the same rule in the drafting step.
- `CurationGuide.md` — the single-link stub scoped to the *no-mechanism-only* case, plus a matching
  path-shape guideline.
- `scripts/quality/prompts/path_coherence_judge.md` — a `no_shortcut_edge` judgment: the semantic
  critic treats the structural shortcut flags as facts, routes the path to `RE_CURATE`, and (since
  this is a structural, not scientific, defect) may name the exact edge to remove.

## Method

Isolated, blinded re-curation (harness at `experiments/shortcut_fix/`, mirroring
`experiments/opus_vs_sonnet/`):

- **Model:** `claude-opus-4-8` — the designated curation agent.
- **Pairs:** 14, all drawn from the prior run (`experiments/opus_vs_sonnet/opus/`, same model,
  pre-fix `AGENTS.md`), **every one of which shortcutted before** — so the before-rate on this set is
  100% by construction. Chosen for diversity: 8 disease areas (cardiovascular, cancer, infectious,
  neurological, autoimmune, metabolic, allergy), path lengths 3–7 edges, and node niches
  (organism-taxon, gene-family, long branch-convergence biologic). P32 (ascorbic-acid deficiency,
  legacy = a 1-link path) is the control that the fix must not over-correct into forcing a mechanism.
- **Isolation:** the agent has 8 tools (`pubmed_search/fetch/probe`, `read_reference`,
  `write/read_path_yaml`, `canonicalize_predicates`, `run_qc`); **none can read `kb/paths/` or any
  gold/legacy curation** — it never sees "what good looks like." Outputs land only under
  `experiments/shortcut_fix/opus/outputs/`, never `kb/paths/`. Each arm has its own PubMed cache; each
  pair is a fresh message history; the task prompt passes drug/disease/IDs only (never the
  `legacy_path_id`). The only difference vs. the baseline run is the fixed `AGENTS.md`.
- **Scoring:** the deterministic, LLM-free `scripts/quality/structural_quality.py`, via
  `experiments/shortcut_fix/score.py`. Metric = fraction of records with `clinical_shortcut` and/or
  `short_circuit` (Issue #2 definition).

## Result — shortcut rate

| | records scored | with a shortcut flag | rate |
|---|---|---|---|
| **Before** (pre-fix) | 14 | 14 | **100%** |
| **After** (post-fix) | 14 | 0 | **0%** |

Every pair collapsed from a shortcut-carrying path to a single clean chain, e.g.:

- **P03 Lisinopril→Hypertension:** before, a full 5-edge ACE→AngII→AT1→vasoconstriction→Hypertension
  chain **plus** a redundant `Lisinopril —treats→ Hypertension` edge (6 edges / 2 paths). After, the
  5-edge chain alone, ending at the disease via `causes` (5 edges / 1 path, fully clean).
- **P02 Atorvastatin→Hypercholesterolemia:** before, the mechanism stopped short and was **bridged
  with `treats`** (which also drew a `type_violation`). After, the agent extended the mechanism all
  the way to the disease (`… → LDL cholesterol —manifestation of→ Hypercholesterolemia`) — no bridge,
  type_violation gone.
- **P08 Cetuximab→Colorectal Cancer:** before, a 3-path multi-branch tangle with a shortcut. After, a
  single `cetuximab ⊣ EGFR → MAPK → proliferation —causes→ Colorectal Cancer` chain.

Per-pair before→after detail is in `experiments/shortcut_fix/analysis.json`.

## Secondary quality observations (honest reporting)

The shortcut fix is clean, but scoring the full structural picture (not just the shortcut metric)
surfaced two things worth recording:

1. **QC:** 14/14 after-outputs pass the full 4-layer QC gate (`ai_curated`). One pair (P37) initially
   Layer-4-failed because it was cut off mid-curation by a sustained Anthropic-API overload window
   (HTTP 529) before finishing its QC iteration — an infrastructure artifact, not a consequence of the
   fix. The runner was hardened with retry-with-backoff on 529/429 to ride out the overload, and P37
   re-curated cleanly (Layer 4 PASS). Notably its `net_polarity` flag persisted across both independent
   curations — confirming that is a real, reproducible mechanism sign error, not noise.

2. **`net_polarity` is not made worse by the fix — the shortcut was *masking* sign errors.** After the
   fix, 4 pairs carry a `net_polarity` HARD flag (the chain reads as not suppressing the disease —
   i.e. a wrong-sign or missing sign-flip step). Cross-checking the *same* pairs before the fix:
   - P16, P26, P37 were scored "coherent" **before only because the negative `treats` shortcut edge
     dominated the polarity product** — their underlying mechanism was already wrong-signed; removing
     the shortcut *exposes* the latent error rather than creating it.
   - P32 already carried `net_polarity` before the fix (pre-existing).
   - Meanwhile the fix **resolved** `net_polarity` on P08 and P21 (flagged before, clean after), where
     the re-curated single chain got the signs right.

   So the redundant shortcut edge wasn't merely restating the conclusion — in several cases it was
   *papering over* real mechanistic sign errors. Catching those is exactly the job of the semantic
   critic's `net_effect_correct` / `missing_step` judgments. The critic step is deliberately **not**
   run in this isolated curation harness (it needs the full pipeline), so these surface here
   unaddressed; in the real `/curate` pipeline they would route to `RE_CURATE`.

## Bottom line

The prompt-and-guide fix, on its own, drives the shortcut/bypass-edge rate from 100% to 0% across a
diverse, adversarial re-curation set — Issue #2's ≤10% bar, met with the maximum possible margin — and
does so while producing valid single-chain paths (14/14 pass full QC). A recommended follow-up
hardening is to make the deterministic shortcut flags *block* (wire
`structural_quality`'s shortcut checks into the pre-edit hook or a 5th QC layer) so the guarantee no
longer depends on model compliance.
