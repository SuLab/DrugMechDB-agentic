# Full-campaign cost estimate + cost-reduction strategy

> **Purpose:** size the cost of forwardfilling all **4,846** records (AI re-curation from scratch)
> so the maintainer can give a go-ahead (issue #6). This is an **estimate with one large unknown**
> (the independent-critic cost, never measured) — a small pilot (#4) is what turns it into a firm
> number.

## Per-path cost model

| Component | Basis | Est. $/path |
|---|---|---|
| **Curation loop** (Opus 4.8, prompt-cached system prefix) | eval measured **$1.59/pair** (Opus, partial capture, ~16.8 iters, no critic) — `experiments/opus_vs_sonnet/` | ~$1.50–2.00 |
| **Independent critic pass** (edge + path judges, grounded via ChEMBL/PubMed tool calls; different model family for independence) | **not yet measured** — largest uncertainty; several grounded model calls per path | ~$0.50–1.50 |
| **Re-curation of bounced paths** (deterministic gate + critic route some fraction back for ≥1 more loop) | eval showed Opus's main defect was the shortcut edge, now HARD-gated (#7) → a re-curation trigger on some fraction; assume ~20–40% need one extra round | ~$0.30–0.70 |
| **Per-path total** | | **~$2.30–4.20** |

**Full corpus:** 4,846 × ~$2.30–4.20 ≈ **~$11,000–$20,000**, likely toward the lower end with the
levers below. Prompt caching and Opus (both the best *and* cheapest curator per #9) are the two
biggest reasons it isn't higher.

## Cost-reduction strategy

1. **Prompt caching (implemented in the engine).** The AGENTS.md + tool-definitions system prefix is
   a large, byte-identical block reused on every turn *and* across back-to-back paths; a
   `cache_control` breakpoint bills its reuse at ~0.1× input. At 4,846 records this is the single
   biggest saver.
2. **Deterministic gate as a cheap pre-filter (implemented, #7).** QC + structural checks are
   deterministic (no tokens). They catch shortcut/topology/schema errors *before* the expensive
   critic runs, and the critic only adjudicates SOFT flags — so we don't spend LLM money re-judging
   hard-bounced paths.
3. **Opus curator (decided, #9).** The eval showed Opus is both the highest-quality *and* the
   cheapest curator (100% vs 80% QC, ~½ the iterations, lower $/pair than Sonnet). Don't "save" by
   downgrading the curator — it costs more in re-curation.
4. **Cheaper independent judge.** Independence (framework §6c) requires a *different model family*
   for the critic, **not** a more expensive one — a cheaper judge model (e.g. Haiku-class) preserves
   the independence benefit at lower cost.
5. **Batches API for the batchable sub-step.** The full multi-turn curation loop can't use the
   Batches API, but a *single-turn* critic sub-judgment can — routing those through Batches captures
   the 50% discount on that slice (the `BatchBackend` skeleton is kept for exactly this).
6. **Iteration cap.** Opus converges by ~17 turns; the cap (MAX_ITERS) prevents a degenerate loop
   from running up cost, and can be tuned down once the pilot shows the real convergence curve.

## Recommendation

**Run a pilot of ~50–100 records first (#4)** through the real engine (curator + critic + gate) to
measure the *actual* per-path cost — especially the critic cost and the true re-curation rate, the
two soft spots above. That converts the ±2× range here into a firm total and is the natural
maintainer go-ahead gate for the full run (#6). Do **not** launch the full 4,846-record run before
that pilot number is in hand.

### See also
- `docs/model_decision.md` (#9) — why Opus (cheapest + best).
- `experiments/opus_vs_sonnet/` — the measured curation cost basis.
- `scripts/campaign_runner.py` / `scripts/curate_engine.py` — where prompt caching + the worker pool live.
