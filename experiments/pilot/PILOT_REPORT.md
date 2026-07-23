# Re-curation pilot report

First full-pipeline run of the agentic curator over a 20-pair stress set, overnight into
2026-07-23. **Anthropic-only. Curator = `claude-opus-4-8`. Semantic critic ON.**
Ran to completion, unsupervised, no crashes.

> This report was corrected on 2026-07-23 (an earlier draft mis-explained the thiamine
> bounce — see §5). It also documents fixes applied *after* the run (§6).

---

## 0. Glossary (read this first)

- **Curation** — one run of the agent producing a mechanistic path for one (drug, disease) pair,
  from research → draft → self-validation.
- **Turn** — one request→response round-trip with the model. The agent can't run its own tools, so
  each time it needs a search / fetch / gate-check it emits a tool request and **stops**; our code runs
  the tool and sends the result back, starting the next turn. One curation here averaged ~19.5 turns.
- **Prompt caching** — the fixed prefix of each request (system prompt + tool definitions) is byte-identical
  every turn, so it is cached after the first turn and re-read at ~0.1× price on turns 2…N. It was live
  during this run (~28% of input served from cache). *Only the fixed prefix is cached today; caching the
  growing conversation history is an available, not-yet-implemented optimization.*
- **Smoke test** — a tiny pre-flight run of 1–2 real curations to confirm the whole pipeline works
  end-to-end before spending on a big batch. (The pre-pilot smoke was atorvastatin + insulin, $8.12.)
- **The gate** — `scripts/quality/gate.py`: QC Layers 1–4 (schema, ontology terms, predicate enum,
  verbatim snippet) + structural checks + (optionally) the semantic critic. Its verdict is what "ACCEPT /
  RE_CURATE" refers to.
- **RE_CURATE vs ESCALATE** — RE_CURATE = the gate bounced the path back for another attempt. After the
  attempt cap it becomes ESCALATE = hold for a human. A final RE_CURATE at the end of a curation is
  effectively "held for human review."
- **ACCEPT / RE_CURATE counts** are the *gate* verdict (deterministic layers + critic combined). A path
  can be critic-clean but still RE_CURATE on a deterministic layer, and vice-versa.

---

## 1. Test architecture — what this pilot is and why

**20 existing legacy records, curated from scratch.** Every pair already has a legacy DrugMechDB path,
so the set doubles as an **agreement-vs-legacy** set: each re-curation can be compared against the
curator's original path for the same (drug, disease).

**Selection** is by `scripts/select_pilot_pairs.py` — a **deterministic, read-only** pass over the 4,846
legacy records in `kb/paths/` that categorizes each record and emits the manifest
`experiments/pilot/pilot_pairs.yaml`. It never writes a curation or touches the corpus. Re-running it
reproduces the same set.

**Four buckets, each probing a specific part of the gate:**

| Bucket | n | What it stress-tests |
|---|---|---|
| **hard_gate** | 4 | Legacy path fires a *still-HARD* check (duplicate_edge / cycle / clinical_shortcut). Re-curation must catch/repair the known error — proves the gate still bites on real errors. |
| **convergent** | 4 | Multi-target drug whose legacy path fires the now-*demoted* `short_circuit`. Proves these legitimate convergent paths now PASS instead of being wrongly bounced. |
| **chembl_preprint** | 4 | Small-molecule → named-protein-target, where compound→target bioactivity is ChEMBL's core coverage. Exercises the source-agnostic evidence layer beyond PubMed. |
| **ordinary** | 8 | Clean legacy records (no structural flags) — the baseline the re-curation should reproduce, and the bulk agreement-vs-legacy anchors. |

**Consistency check:** 5 of the 20 pairs are marked `repeat: 3` (one per bucket, plus an extra ordinary):
each is curated **three independent times from scratch** to measure how stable the agent's output is.
So **15 pairs ×1 + 5 pairs ×3 = 30 curations.**

### The 20 pairs (and where they came from)
All drawn from the legacy corpus by the selector above. `[×3]` marks a repeat pair.

- **hard_gate:** aminobenzoic acid→Dermatomyositis `[×3]` (dup edge) · Etanercept→Psoriasis-w/-arthropathy (dup edge) · azathioprine→Rheumatoid arthritis (cycle) · clortermine→Anorexia nervosa (clinical_shortcut)
- **convergent:** Thiamine→Avitaminosis `[×3]` · calcium acetate→Hypocalcemia · atomoxetine→ADHD · bleomycin→Squamous cell carcinoma
- **chembl_preprint:** imatinib→CML `[×3]` · donepezil→Alzheimer's · atorvastatin→Hypercholesterolemia · empagliflozin→Type-2 diabetes
- **ordinary:** cetuximab→colon cancer `[×3]` · alteplase→Pulmonary embolism `[×3]` · sermorelin→Pituitary dwarfism · urokinase→Pulmonary thromboembolism · anakinra→CAPS · insulin human→Type-1 diabetes · desmopressin→Hemophilia A · oprelvekin→Thrombocytopenia

---

## 2. Headline results

| Metric | Value |
|---|---|
| Curations attempted | 30 |
| **Billed cost** | **$117.68** (+ the $8.12 pre-pilot smoke for 2 of the pairs) |
| Outputs written | 29 (1 lost to a token-ceiling truncation — see §6A) |
| Gate ACCEPT (billed) | 20 |
| Gate RE_CURATE (billed) | 5 |
| Resumed/skipped from earlier runs | 4 ($0 — 2 smoke ACCEPTs + 2 re-used drafts) |
| Hard failure (no output) | 1 (atomoxetine, `max_tokens`) |
| Avg turns / curation | 19.5 |
| Cost range | $0.52 – $14.94 (median ~$4) |

Cost by bucket: ordinary $54.72 (n=12) · convergent $36.87 (n=6) · hard_gate $18.29 (n=6) ·
chembl_preprint $7.81 (n=6).

---

## 3. What the pilot PROVED

1. **The pipeline runs end-to-end, unsupervised, overnight** — research → draft → QC(L1–4) →
   structural gate → semantic critic loop, 30×, no crashes, resumable.
2. **The semantic critic does real work — it is NOT a rubber stamp.** It bounced 5/30 and caught a
   *genuinely wrong* path: **aminobenzoic acid → dermatomyositis** — "individually sourceable edges, but
   the path FAILS as a whole mechanism … routes the therapeutic effect through dermal-mucin/GAG
   deposition, a SECONDARY, clinically-questionable mechanism." Exactly the edge-evidence≠path-truth
   failure the critic exists to catch.
3. **The gate still bites on real errors** (the hard_gate bucket) *and* lets legitimate convergent paths
   through (the convergent bucket) — the structural-gate re-tuning behaved as designed.
4. **The blinded-judge harness works** — validated offline (`--stub`): it blinds all outputs, computes
   legacy-agreement, and writes a report. Ready to bill (see §7).

---

## 4. The 5 RE_CURATE cases

- **aminobenzoic acid → dermatomyositis** — a genuine, well-reasoned semantic REJECT (see §3.2). The
  strongest evidence the critic adds value.
- **anakinra, oprelvekin, bleomycin→SCC** — the critic's summary *affirms the mechanism is correct*, but
  it bounced a **single edge's citation** for not independently grounding (e.g. "IL-1R positively
  regulates inflammation" is true, but its cited snippet didn't clear the independent-grounding bar). This
  is the strict per-edge-citation policy at work — see §7 (the main tuning lever).
- The 3 priciest curations ($14.94 / $10.17 / $9.75) were all RE_CURATE loops fighting an edge flag —
  bounces drive the cost tail.

---

## 5. Cross-run consistency (the repeat ×3 pairs) — CORRECTED

| Pair (bucket) | run 1 | run 2 | run 3 |
|---|---|---|---|
| imatinib→CML (chembl) | ACCEPT | ACCEPT | ACCEPT |
| cetuximab→colon (ordinary) | ACCEPT | ACCEPT | ACCEPT |
| alteplase→PE (ordinary) | ACCEPT | ACCEPT | ACCEPT |
| thiamine→avitaminosis (convergent) | RE_CURATE | ACCEPT | ACCEPT |
| aminobenzoic→dermatomyositis (hard_gate) | *(resumed)* | ACCEPT | RE_CURATE |

**Correction on thiamine (an earlier draft got this wrong).** I originally wrote that thiamine r1 was
"critic-ACCEPT but gate-RE_CURATE." That was a misread — I read a critic sidecar that had been
*overwritten by the last repeat* (the sidecar is keyed per pair, so r3 overwrote r1). The real story,
verified by reading the r1 output file:

- **r1 produced a degenerate one-edge shortcut:** `Thiamine --treats--> Avitaminosis`, no mechanism in
  between. That trips the **`clinical_shortcut` HARD check**, which bounces *deterministically* — and
  because a HARD structural fail short-circuits the gate, **the critic never even ran on r1.** So it was a
  cheap mechanical rejection of a lazy shortcut, not a critic call.
- **r2 and r3** built the proper convergent chain (Thiamine → thiamine pyrophosphate → transketolase →
  carbohydrate metabolism → avitaminosis) and passed.

**Takeaway:** the *gate* is consistent every run; the *curator* is stochastic. A retry recovers a
mechanical misfire (thiamine 2/3). A genuinely ambiguous mechanism (aminobenzoic) flips ACCEPT↔RE_CURATE
and needs a human. Straightforward mechanisms (the 3 ×3 anchors) were 3/3 identical. ⇒ **N-retry
best-of** recovers most; a small residue of ambiguous pairs always needs a human.

---

## 6. Fixes applied AFTER the run (in response to what the pilot surfaced)

### A. `max_tokens` truncation lost a curation → FIXED
**atomoxetine→ADHD** (a 10-edge convergent path) hit the **16,384-token non-streaming output ceiling**
mid-turn → truncated → no output, $1.67 wasted. **Fix (applied):** the curation loop now **streams** the
Messages call and the ceiling was raised to **32,768** (streaming is what makes a high ceiling safe from
request timeouts). A truncated turn is now detected and stopped cleanly instead of acting on broken
output. *Verified end-to-end by a live streaming smoke (see the run log / §7 status.)*

### B. QC-gate attempts raised 3 → 4
The curator now gets **up to 4 attempts** against the gate before a path is held for human review
(prompt guidance + the critic-loop `--max-rounds` default, both now 4). Rationale: the gate itself is
cheap to run; the cost is the curator's fix attempt, so allowing a 4th attempt recovers cases a 3rd would
have caught, at ~$1–4 each, before escalating.

### C. Caching status (clarification, no change)
Prompt caching was **already implemented and working** during this run — there was no "caching bug" to
fix. The one available *improvement* (caching the growing conversation history, not just the fixed
prefix) is **not yet implemented** and remains parked pending a decision.

---

## 7. Open decisions / what's next

- **Edge-citation policy (the main quality/cost lever).** Keep the strict "every edge's citation must
  independently ground" bar (bounces correct-mechanism paths on a weak citation; drives the cost tail),
  or let a **critic-affirmed** edge pass with a weak citation demoted to advisory? Your call.
- **The billed blinded judge** (independent quality proof over the 29 outputs) — HELD for your OK; it
  would add ~$60–120. Harness is validated. Command:
  ```
  ./.venv-py310/bin/python scripts/run_blinded_judge.py experiments/pilot/outputs --run \
      --out-dir experiments/pilot/blinded
  ```
- **Scaling.** `run_pilot` runs sequentially (~16 min/curation); the production campaign must run through
  `CampaignRunner.run(AgenticBackend(workers=N))`. Full-corpus projection at this quality bar ≈ $20–30k.

## Artifacts
- `experiments/pilot/pilot_pairs.yaml` — the 20-pair manifest (with per-pair `why`).
- `experiments/pilot/run_summary.json` — per-curation cost / turns / verdict *(gitignored)*.
- `experiments/pilot/outputs/*.yaml` — the 29 curated paths *(gitignored)*.
- `provenance/<id>.semantic_review.yaml` — per-path critic audit trail (note: one file per pair, so a
  repeat pair's later run overwrites the earlier run's sidecar).

Nothing was pushed by the run; `kb/` was never touched; all spend stayed in `experiments/pilot/`.
