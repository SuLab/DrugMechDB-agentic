# Phase 3 Evaluation — Sample selection methodology

**PRD reference:** [PRD v3 §6 Phase 3](PRD_v3.md)
**Date:** May 2026
**Pair list (machine-readable):** [phase3_eval_pairs.yaml](phase3_eval_pairs.yaml)

## Exit criteria from PRD v3

- AI-generated paths pass Layers 1–4 under `ai_curated` on **first attempt** for **≥80%** of the 30-case eval set.
- Median curator time-to-review on the 30 cases is **<15 minutes**.

## Why 30 (and why stratified)

- v2 specified 10 pairs; v3 grew this to ≥30 because a 10-case run has ±15-percentage-point margin on the 80% target (Wilson 95% CI), which leaves the pass/fail decision essentially indistinguishable from noise. 30 narrows the CI to ±7 pp — enough to gate Phase 4.
- Stratification ensures the eval covers the **modes of failure** the agent will face in production, not just the easy paths. A 30-case set that's all cardiovascular tells us nothing about how the agent handles, say, retroviral antivirals or rheumatology biologics.

## Stratification

The 30 pairs are sized 5 per drug class × 5 per disease area (where available; some intersections are 0). The plan covers **6 drug classes and 6 disease areas** (PRD requires ≥5 of each):

| Drug class | Pairs | Disease areas covered |
|---|---|---|
| Cardiovascular | 5 | Cardiovascular |
| Oncology | 5 | Cancer |
| Antimicrobial | 5 | Infectious disease |
| CNS / Neurology | 5 | Neurological / psychiatric |
| Immunomodulator | 5 | Autoimmune |
| Endocrine / Metabolic | 5 | Metabolic |
| **Total** | **30** | **6 areas** |

## In-corpus vs. net-new

A second dimension stratifies between pairs that already exist in DrugMechDB (so the agent's path can be compared against curator work) and pairs that are net-new:

| | Count | Why include |
|---|---|---|
| In-corpus (exact legacy `(drug_mesh, disease_mesh)` match) | 16 | Calibration — measures how close the agent's mechanism resembles human curation when the answer is known. Outputs land in `tests/phase3_eval_outputs/`, not `kb/paths/`, so legacy curation is preserved untouched. |
| Net-new (no legacy path for this exact pair) | 14 | The real product-test — measures whether the agent can curate paths that don't yet exist. Includes pairs where a related path exists for a different disease MESH (e.g. cetuximab + colorectal MESH:D015179 vs. legacy MESH:D003110 colon). |

## Pair selection criteria

Within each class, pairs were chosen on three criteria:

1. **Well-described mechanism in the public literature.** A 20-30 PMID corpus should be findable for each pair. If literature scarcity is the bottleneck, the eval measures the wrong thing (PubMed coverage, not agent quality).
2. **A single dominant mechanism.** Drugs with multiple distinct mechanisms (e.g. modafinil) are deferred — they conflate "did the agent succeed" with "did the agent pick the same mechanism a curator would."
3. **Mainstream therapeutic relevance.** Orphan-disease or recently-approved drugs are deliberately under-represented in this set; Phase 3 measures the platform's baseline, not its tail.

## What is *not* measured by this eval

These are real product questions but they're scoped out of Phase 3 by design — addressed in later phases:

- **Cross-curator agreement.** The eval scores against the QC pipeline (deterministic), not against multiple human reviewers. PRD §8 governance.
- **Path quality / mechanism plausibility beyond schema correctness.** The QC layers check structure, ontology binding, predicate validity, and snippet verbatim — not "is this the *right* mechanism." Plausibility is a curator-review question; the eval measures the median curator review time as a proxy (target: <15 minutes/pair).
- **Backfill performance.** The `/backfill` skill is exercised in Phase 4 alongside the dashboard launch (PRD §5.2 / §6 Phase 4).
- **Sustained pass rate over weeks.** This is a one-shot snapshot. The CI-gated rolling 30-day KPI in PRD §2 starts measuring after Phase 4 deploys the GitHub Actions workflow.

## Eval execution model

Each pair is curated by an **isolated** Claude session running the `/curate` slash command from `.claude/commands/curate.md`, with eval-mode overrides:

- Output directory: `tests/phase3_eval_outputs/<pair_id>.yaml` (not `kb/paths/`).
- The agent must NOT modify `kb/paths/_index.yaml`.
- All other AGENTS.md rules apply unchanged.

The [`scripts/run_phase3_eval.py`](../scripts/run_phase3_eval.py) tool is the bookkeeping layer:

| Subcommand | What it does |
|---|---|
| `prompt P01` | Emits the curation prompt for one pair (for piping into an agent session or copy/paste). |
| `list` | Shows all 30 pairs with their stratification and current output status. |
| `score [P01 ...]` | Runs `qc.py --profile ai_curated --json` against each output and tabulates layer-by-layer results. Writes `docs/phase3_eval_results.json`. |
| `report` | Generates `docs/phase3_eval_results.md` (the final scoring table for the PRD exit gate). |

Each agent run is independent — there is no shared state between pairs beyond the immutable schema, scripts, and `references_cache/` (PubMed abstracts can be reused across pairs that cite the same paper).

## Scoring rule

A pair counts as **first-pass pass** iff `qc.py --profile ai_curated` reports `overall_pass: true` on the agent's **initial** output (after the agent's internal canonicalization step — which is part of AGENTS.md §5.6 — but BEFORE any human edit). The retry budget (up to 3 in-agent loops) is *not* counted against first-pass; only post-hoc human edits would.

Why this rule: in production, an agent that lands a valid file after 2 internal retries is functionally equivalent to one that gets it on attempt 1 — the user experience is identical. The retries are the agent's loop, not the curator's.

If an output cannot pass within 3 retries and ships with an `## Unresolved validation failures` section, it counts as **fail** for this eval — but the agent has correctly surfaced the problem, which is itself a feature (PRD §5.1.3).

## Curator time measurement

Curator review time is recorded out-of-band by the curator (not the agent or scripts). The 30 pairs will be reviewed in random order by the same curator across a single sitting; per-pair start/stop times are logged in the eval results file under a `curator_review_seconds` field that the curator fills in.

Median-time interpretation: this is the *additional* review beyond the agent's self-validation — i.e. the curator is checking facts, not rerunning the QC pipeline.

## Result reporting

After execution, the final results go in [phase3_eval_results.md](phase3_eval_results.md) (generated by `run_phase3_eval.py report`) with:

- Pairs attempted vs. set size
- First-pass pass count and rate
- Per-layer pass rates (which layer fails most?)
- Pass rate split by drug class, by disease area, and by in-corpus vs. net-new
- Median and distribution of curator review time
- A pointer to per-pair YAMLs and QC outputs

If the first-pass rate is <80%, the report includes a root-cause breakdown (which layers failed, which patterns recurred) and a proposed AGENTS.md tightening to land before re-evaluation.
