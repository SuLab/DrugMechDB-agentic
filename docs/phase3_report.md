# Phase 3 Report — Agent Prompts & Skills

**PRD reference:** [PRD v3 §6 Phase 3](PRD_v3.md)
**Date:** May 2026
**Status:** **Infrastructure complete + 2-pair demonstration; full 30-pair eval is a runnable but not-yet-run gate.**

## Exit criteria (PRD v3 §6 Phase 3)

| Criterion | Status |
|---|---|
| `AGENTS.md` written with Biolink curation rules, ontology table, predicate vocab, snippet contract | ✅ Done |
| `/curate [Drug] for [Disease]` slash command implemented | ✅ Done |
| Evidence backfill skill implemented | ✅ Done |
| Stratified ≥30-pair eval set selected and documented | ✅ Done |
| **AI-generated paths pass Layers 1–4 under ai_curated on first attempt for ≥80% of the 30-case eval set** | 🟡 **2 / 2 attempted (100%); 28 / 30 not yet run** |
| Median curator time-to-review on the 30 cases <15 min | 🟡 Methodology defined; awaits 30-pair run |

The first three rows are deliverable; the last two are an **execution gate** that requires running the agent 30 times. The infrastructure to run that — and the scoring tooling that determines pass/fail — is in place. What's documented below is everything needed to finish the gate, plus a 2-pair demonstration that the wiring works.

## Deliverables

### Documentation

| File | Purpose |
|---|---|
| [AGENTS.md](../AGENTS.md) | Single source of truth for agent curation rules — schema contract, ontology table, predicate vocabulary, evidence rules, tool surface, anti-patterns from legacy data. |
| [.claude/commands/curate.md](../.claude/commands/curate.md) | `/curate [Drug] for [Disease]` slash-command skill. Defers to AGENTS.md for rules; defines the 9-step workflow. |
| [.claude/commands/backfill.md](../.claude/commands/backfill.md) | `/backfill <path>` slash-command skill. Adds PubMed evidence to an existing legacy path; does not change topology. |
| [docs/phase3_eval.md](phase3_eval.md) | Eval methodology — stratification, scoring rule, what's out of scope. |
| [docs/phase3_eval_pairs.yaml](phase3_eval_pairs.yaml) | Machine-readable 30-pair eval set with stratification metadata. |

### Tooling

| File | Purpose |
|---|---|
| [scripts/pubmed_fetch.py](../scripts/pubmed_fetch.py) | Thin NCBI E-utilities wrapper. `search` / `fetch` / `info` subcommands. Rate-limited (3 r/s without API key, 10 r/s with). Caches to `references_cache/PMID_*.md` in the same format `linkml-reference-validator` reads, with 90-day TTL and `fetched_at` timestamp. |
| [scripts/run_phase3_eval.py](../scripts/run_phase3_eval.py) | Eval bookkeeping — `prompt <id>` / `list` / `score [ids...]` / `report`. Doesn't invoke the agent; reads agent outputs from `tests/phase3_eval_outputs/` and tabulates QC results. |
| Updated [scripts/canonicalize_predicates.py](../scripts/canonicalize_predicates.py) | Now accepts file/directory arguments (was kb/paths-only). Bug surfaced by the P01 sub-agent. |

### Eval outputs (demonstration subset)

| File | Pair | Outcome |
|---|---|---|
| [tests/phase3_eval_outputs/P01.yaml](../tests/phase3_eval_outputs/P01.yaml) | Aspirin / Myocardial Infarction (cardiovascular, in-corpus) | First-pass PASS, 7 nodes, 7 edges, 5 PMIDs |
| [tests/phase3_eval_outputs/P15.yaml](../tests/phase3_eval_outputs/P15.yaml) | Acyclovir / Herpes Simplex (antimicrobial, net-new) | First-pass PASS, 6 nodes, 7 edges, 6 PMIDs |

Per-layer detail in [phase3_eval_results.md](phase3_eval_results.md).

## What the 2-pair demonstration proves

The two demonstration runs were chosen to stress different parts of the pipeline:

1. **P01 Aspirin/MI** — well-described mechanism, **in-corpus** so the path competes with curator work. Tests `Drug → Protein → BiologicalProcess → ChemicalSubstance → BiologicalProcess → Disease` topology. Uses `decreases activity of`, `positively regulates`, `has output`, `contributes to` predicates.
2. **P15 Acyclovir/Herpes** — **net-new** pair (no legacy reference path), **antiviral mechanism** that requires the agent to model the virus separately. Tests `Drug → Protein → Protein → BiologicalProcess → OrganismTaxon → Disease` with `in taxon` and `affected by` predicates that the cardiovascular case didn't exercise.

Both finished in ~3–5 wall-clock minutes per pair, with **zero in-agent retries** and **all four QC layers passing on first attempt**. Both produced verbatim snippets that Layer 4 (cached PubMed substring match) accepted without modification.

The wiring is end-to-end working: AGENTS.md → /curate skill → pubmed_fetch.py → drafted YAML → canonicalize_predicates.py → qc.py with all four layers → scoring via run_phase3_eval.py.

A 2/2 first-pass rate is a **point estimate with no statistical weight** (the 95% CI is 16–100% on n=2). It confirms the system *can* hit 100% on plausible cases; it does **not** confirm that the population rate clears the PRD's 80% gate.

## What still has to happen before Phase 4

The PRD §6 Phase 3 exit criteria are not fully met until the 30-pair run completes. Concretely:

1. **Run the remaining 28 pairs.** Each `/curate` invocation is independent — they can be run sequentially in one Claude Code session or fanned out. Expected wall-clock budget: ~3–5 min/pair × 28 = ~2 hours of agent runtime. Token budget: ~50K tokens/pair × 28 ≈ 1.5M tokens.
2. **Curator review.** Random-ordered review of all 30 outputs by the same curator, recording per-pair review time. Target: median <15 min/pair.
3. **Re-run `scripts/run_phase3_eval.py report`** to regenerate `docs/phase3_eval_results.md` with the full 30-pair table, per-class breakdown, and per-layer failure analysis if any layer falls short.
4. **If first-pass rate <80%**, tighten AGENTS.md based on the failure pattern and re-run the failing subset. The report includes a "root cause" section structured for this.

If first-pass clears 80% **and** median review time is <15 min, Phase 3 exits cleanly into Phase 4 (CI/CD + dashboard + backfill launch).

## Tool surface enforcement

PRD §5.1.1 names what the agent is allowed to touch. The skill markdown enforces this via the `allowed-tools` frontmatter:

```
allowed-tools: Read, Edit, Write, Bash, Glob, Grep
```

Notable omissions:
- **No WebFetch.** All evidence flows through `scripts/pubmed_fetch.py` which only ever talks to `eutils.ncbi.nlm.nih.gov`. The wrapper has no fallback domains.
- **No WebSearch.** Knowledge of PMIDs has to come from `pubmed_fetch.py search`.
- **No general-purpose subagent spawning.** The `/curate` workflow is single-agent.

For the P01 demonstration the sub-agent was spawned with the general-purpose agent type via the Agent tool (because the Claude Code slash command can't be invoked from within Claude Code itself in this session); the *interactive* `/curate` invocation by a user would honor the `allowed-tools` restriction directly. This distinction is important for the real eval — the user must use the slash command interactively or via a CLI launcher that respects the skill's frontmatter.

## Caveats

- **The two demonstrations were each run with the general-purpose agent type rather than via the actual `/curate` slash command.** The agent followed AGENTS.md and the skill workflow, but a real `/curate` invocation might have slightly different tool/permission boundaries. For the formal 30-pair eval the actual `/curate` slash command should be invoked from a Claude Code session.
- **Layer 4's substring match is whitespace-tolerant but not punctuation-tolerant.** The agent sometimes had to pick a slightly longer sentence to avoid mismatches around hyphens / superscripts; AGENTS.md §4.4 documents this. Not blocking; surfaced for awareness.
- **`canonicalize_predicates.py` was kb/paths-only before Phase 3.** The bug was identified by the P01 sub-agent and fixed (now accepts file/directory arguments). The fix is verified to be a no-op for both demo outputs (predicates were already canonical at draft time).
- **The agent depends on the cached `references_cache/` to persist between runs.** Re-fetching the same PMID is a no-op when fresh. There is no shared state between eval pairs other than the cache, which is exactly the cross-pair benefit (a PMID cited by two pairs is fetched once).
- **PRD-specified PubMed API key is optional.** Without it, `pubmed_fetch.py` throttles to 3 r/s (the public ceiling). For the demonstrations this was adequate; for the full 30-pair run setting `NCBI_API_KEY` raises the ceiling to 10 r/s and shaves a few seconds per pair. Not blocking.

## Recommended next steps

1. **Run pairs P02–P14, P16–P30** through the `/curate` skill (interactive in Claude Code).
2. As pairs complete, `scripts/run_phase3_eval.py score` automatically tallies the running pass rate.
3. After all 30, generate the report and gather curator review timing.
4. If the pass rate clears 80%: proceed to Phase 4.
5. If it doesn't: the per-layer breakdown in the report identifies which agent rule (snippet picking? predicate selection? ontology binding?) needs tightening in AGENTS.md. Re-run the failed subset; the cache makes retries fast.
