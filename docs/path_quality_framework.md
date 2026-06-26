# Path-Quality Measurement Framework

> **Status:** design proposal. Authored as the answer to the
> recurring "how do we know a curated path is *good*?" question — the pivotal gate behind the
> 30-pair eval and the decision of whether to backfill legacy paths or re-curate them.
> **Scope:** defines how to measure curation quality *above* the syntactic QC floor (`scripts/qc.py`
> Layers 1–4). References real artifacts in this repo so it can be built against, not just read.

---

## 1. The problem: the QC gate measures *well-formedness*, not *truth*

Everything in the current 4-layer gate (`scripts/qc.py`) is a **syntactic / structural** check:

| Layer | Script | Question it answers | What it is blind to |
|-------|--------|---------------------|---------------------|
| 1 schema | `validate_schema.py` | Is this a well-formed `MechanisticPath`? | — |
| 2 ontology | `validate_node_ontology.py` | Are the CURIEs real and correctly typed? | — |
| 3 predicate | `validate_predicates.py` | Is `key` one of the 67 allowed predicates? | Is it the **right** predicate? |
| 4 reference | `validate_references.py` | Is the snippet a verbatim substring of the PMID? | Does the snippet **establish this edge**? |

This is proven by `docs/phase3_model_comparison.md`: Opus 4.8 and Sonnet 4.6 both scored **5/5
first-pass, 0 retries, 100% `SUPPORT`**. *The gate cannot tell the two models apart.* It is
saturated and binary, so above the syntactic floor, "quality" is currently **undefined**.

Two structural traps make this concrete:

- **`supports` is self-graded and unchecked.** The schema (`drugmechdb.yaml`) defines
  `EvidenceSupportEnum` = {SUPPORT, PARTIAL, NO_EVIDENCE, REFUTE, WRONG_STATEMENT}, but Layer 1
  only verifies the value is *in the enum* — never that it is *true*. And it is filled in by the
  **same agent that wrote the edge**: an unblinded, single-rater self-grade. Every eval edge says
  `SUPPORT` because its author said so. Nobody checks.
- **Verbatim ≠ on-topic.** Layer 4 proves the words appear in the source; it cannot see whether
  they are about the right entity or the right relation.

### The canonical failure: `tests/phase3_eval_outputs/P06.yaml` (Tamoxifen → Breast Neoplasms)

P06 passes all four layers, yet:

1. **Edge 1** `Tamoxifen --decreases activity of--> Estrogen receptor` is supported by a snippet
   that is **about endoxifen**, not tamoxifen — *"Endoxifen is a potent antiestrogen that binds and
   blocks estrogen receptor alpha…"*. The snippet's **subject ≠ the edge's subject**. (The
   `explanation` even admits it: "Endoxifen is the active metabolite of tamoxifen.")
2. **Edge 3** `proliferation --positively correlated with--> Breast Neoplasms` **reuses the edge-2
   snippet** (PMID:42210419, about ERα's role) — it does not establish edge 3 at all.
3. **Edge 4** `Tamoxifen --treats--> Breast Neoplasms` is a **redundant shortcut** that
   short-circuits the whole mechanism, backed by a **single case report**.
4. Nearly every item is tagged `evidence_source: IN_VITRO`, but the snippets are
   definitional/review sentences, not in-vitro experiments — the source labels are self-assigned
   and wrong.

All four are invisible to the gate. Closing that blind spot is the goal of this framework.

---

## 2. Quality is a *vector*, not a scalar

Do not collapse quality to one number prematurely — that just re-hides subjectivity. Score it as a
profile, then let the **keep/reject threshold and the weighting be a maintainer decision** (it encodes
what DMDB should optimize):

| Component | Type | What it produces |
|-----------|------|------------------|
| **Hard gates** | binary, must-pass | schema · ontology · verbatim · **net-polarity-negative** · connectivity. Fail any → reject. |
| **Edge-faithfulness score** | graded | fraction of evidence items where the *independently re-derived* `supports` = SUPPORT and matches the curator's self-grade |
| **Path-validity score** | graded | parsimony · topology · coverage |
| **Confidence signal** | graded | self-consistency across N independent curations |
| **Reference agreement** | graded (when gold exists) | semantic agreement with the legacy path + adjudication label |

These map onto **new semantic layers 5–7** stacked on the existing syntactic Layers 1–4.

---

## 3. Layer 5 — Edge-evidence faithfulness (the atomic ladder)

The mistake is treating "does this evidence support this edge?" as one holistic judgment. It
decomposes into a short pipeline of **narrower checks**, most of which are entity-linking or
textual-entailment problems — bounded, cheap, and calibratable — not "is this good biology?".

An edge is a triple `(subject_CURIE, predicate, object_CURIE)` + a snippet + a source. Run each
evidence item through:

| # | Check | Method | P06 failure it catches |
|---|-------|--------|------------------------|
| 1 | **Verbatim integrity** — snippet appears verbatim in source | script (≈ existing Layer 4) | — |
| 2 | **Subject grounding** — snippet's subject entity = edge `source` | entity-linking (OAK/BioThings) + model fallback | endoxifen ≠ tamoxifen |
| 3 | **Object grounding** — the thing the relation *acts on* = edge `target` (not just "mentioned") | entity-linking + model | (P10: HER2 named, but PI3K is what's decreased) |
| 4 | **Polarity** — increase / decrease / neutral matches predicate sign | model (classification) | — |
| 5 | **Direction** — subject acts on object, not the reverse | model | — |
| 6 | **Granularity** — `decreases activity of` vs `…abundance of` vs `…expression of` | model | — |
| 7 | **Modality / scope** — asserted as established vs hedged / context-bound | model | (review sentence ≠ assertion) |
| 8 | **Source-type correctness** — `evidence_source` accurate + policy-appropriate | metadata + model | IN_VITRO on a review sentence |

**Output space is already defined.** The judge does not invent a rubric — it **independently
re-derives the `EvidenceSupportEnum` value** and flags any disagreement with the curator's
self-assigned one. On P06 edge 1, an honest judge returns `PARTIAL` (right entity family, wrong
specific entity), not `SUPPORT`. *That delta is the quality signal — a label, not a vibe.*

Checks 1–3 are mostly automatable (string + entity-linking); 4–8 are entailment-style
classification. None require the judge to "know biology" — they require it to read.

---

## 4. Layer 6 — Path-level validity (edge-evidence ≠ path-truth)

Layer 5 verifies each edge against its evidence. But a path of individually-supported edges can
still fail to be the *mechanism* (the project's founding principle). So a second tier checks the
**graph as a whole**:

- **Net polarity — the deterministic core; build this first.** Assign each of the 67 predicates a
  sign: `decreases activity of` = −1, `positively regulates` = +1, contextual predicates
  (`in taxon`, `occurs in`, `molecularly interacts with`) = 0/neutral. Collapse the path to its
  signed backbone and **require the product drug→disease to be negative** (disease ends up
  decreased). Fully deterministic; needs only a small maintained sign table; encodes a curation
  convention currently enforced only by eyeball. **Highest-leverage objective check available.**
- **Parsimony / redundancy** — flag any edge whose removal leaves the path still connected and
  still net-negative (a candidate shortcut/spurious edge). *Auto-catches P06's `treats` shortcut
  and P10's double-HER2 edge*; the model only judges whether a redundant edge is a genuine
  convergent mechanism or noise.
- **Topology convention** — starts `Drug → Protein target`; 3–7 links; branch only on convergence.
  Mostly scriptable.
- **Coverage (the genuinely hard one)** — "is a critical intermediate step missing?" *Cannot* be
  made objective without a reference path or a curated pathway oracle. This is the residual that
  stays human-anchored (see §8).

---

## 5. Layer 7 — Semantic agreement with the gold path

For in-corpus pairs (those with a `legacy_path_id`), an expert path already exists, so agreement is
measurable — but with two non-negotiable cautions:

- **Compare semantically, not by exact CURIE/predicate match.** Normalize entities and compare
  predicates *up to the Biolink-version translation* — otherwise vocabulary drift (the 51.5%
  predicate aging the drift audit found) registers as a quality disagreement when it is not.
- **Disagreement ≠ error.** The legacy set is not perfect. Divergence routes to **adjudication**,
  and the **adjudication outcome distribution — agent-wrong / agent-better / both-valid — IS the
  evidence needed** to decide whether to backfill or re-curate legacy paths. High agreement =
  reproduces expert consensus; divergence = the interesting cases.

---

## 6. The judge agent: qualified by *grounding*, not *intelligence*

The sharpest logistics question is "how is a second agent qualified to grade the first?" The answer
is a reframe.

**Checking is easier than generating only when there is a referent external to the checker's own
beliefs.** If curator and judge are the same model family, the judge's "knowledge" is the *same
parametric memory* that produced the curation — so it rubber-stamps plausible-but-wrong edges
(exactly why self-graded `SUPPORT` is meaningless). Verification reliability comes from the
external referent, not the judge's IQ. Three design rules follow:

**(a) The judge reads *broader and independent* sources than the curator.** The conservative-
sourcing boundary constrains what the *curator* may use as a curation **input**; it does **not**
constrain what the *verifier* may read to **check** a claim. Grounding is a **fallback hierarchy**,
not a single dependency:

1. **ChEMBL `get_mechanism`** — independent, expert-curated drug→target→action records. Almost
   every DrugMechDB path starts `Drug → (its target)`, so this grounds the most important edge in
   the corpus with a structured lookup and no NLI. *Verified example:* `get_mechanism(CHEMBL83)`
   (tamoxifen) returns target `CHEMBL206` (estrogen receptor alpha), `MODULATOR`,
   `direct_interaction: true`, with DailyMed + PubMed + Wikipedia refs — grounding P06 edge 1
   independently of the endoxifen snippet. *(It also illustrates the granularity nuance: ChEMBL's
   general label is "modulator/mixed agonist-antagonist"; "decreases activity of" is correct only
   in the breast-cancer context — a scope check, not a contradiction.)*
2. **Other structured oracles** — DrugBank MoA, UniProt (protein function), Guide to Pharmacology;
   GO / Reactome for downstream pathway edges.
3. **Entailment over the cited text** — the §3 ladder; needs no database, works for any edge with a
   snippet.
4. **Abstain → human.** If nothing independent can ground the edge, the judge reports
   "ungroundable" — a **low-confidence flag, never a silent pass.**

   *On ChEMBL coverage:* the ChEMBL **mechanism table** is a curated subset (a few thousand drugs),
   even though ChEMBL overall is huge — but it is biased toward *exactly* our population (approved
   drugs with established MoA). A drug's absence doesn't break anything; that edge simply drops from
   tier 1 to tier 2/3, or to abstention at tier 4. Likely tier-3/4 cases: old drugs, combination
   products, some biologics/peptides, MESH-C substances with no clean single target — a minority,
   and exactly the ones a human should see anyway.

**(b) Cite-or-abstain.** Every verdict must cite the specific retrieved span or DB record it rests
on. A judge that cannot point to external evidence **abstains and routes to a human** — it does not
guess from memory. This also makes the judge itself auditable and calibratable.

**(c) Different model family for judge vs curator.** The harness already runs multi-provider
(`claude` / `openai` / …). Curate with one, judge with another — the cheapest possible independence
boost; it breaks the shared-prior problem at near-zero cost.

Net: the judge is qualified like a referee with the rulebook and instant replay — not by being a
better athlete, but by having access to evidence and a bounded set of calls to make.

---

## 7. Calibration — what makes any of this defensible

An LLM quality number that has not been checked against human judgment is just hidden subjectivity.
So:

- Score a sample with a **blinded, ≥2-rater human rubric** (raters do not know which model/provider
  produced which path — the flaw in the original unblinded comparison), and report **inter-rater
  agreement (Cohen's κ)**.
- Validate the judge against those human labels **per sub-check, not globally.** The judge will
  likely be strong on verbatim / polarity / entity-linking and weak on coverage. **Auto-trust the
  judge only on the sub-checks where its κ vs. humans clears a threshold; keep the rest
  human-routed.** Per-check calibration is far more defensible than one global "is the judge good?"
  number.

**Self-consistency** (run a pair through N independent curations) is a *confidence/triage* signal,
not a truth signal — N runs can share the same hallucination. Read it as: convergent **and**
externally grounded = high confidence; convergent but ungroundable = *suspicious* → human.

---

## 8. What stays hard / open decisions (surface, don't silently bake in)

- **Coverage / "missing critical step"** cannot be made fully objective without a reference or a
  curated pathway oracle. Honest residual; gold-anchoring (§5) + self-consistency + human carry it.
- **Scalar keep-threshold + component weighting** is a value judgment about what DMDB optimizes —
  **a maintainer decision**, not an engineering one.
- **Evidence-source policy** (PubMed-only verbatim per PRD vs. secondary-assertion per the project's
  sourcing policy) changes which §3 check #1 and #8 enforce. Settle before a large run.
- **Biolink-version translation** must be fixed before §5's semantic comparison can be trusted.

---

## 9. Recommended first build (cheapest proof of signal)

1. **Net-polarity checker** (§4) over all 4,846 records — deterministic, no calibration needed; see
   how many *legacy* paths it flags. Pure read on how much signal the approach surfaces.
2. **ChEMBL-grounded first-edge verifier** (§6 tier 1) — independent oracle, covers the single most
   important edge in every path, no NLI.

Both together would have flagged real problems in P06 and P10 that all four current layers waved
through — the cheapest possible demonstration that quality is measurable above the syntactic
floor, and infrastructure that serves *either* the backfill or the re-curation outcome.

---

### Artifacts referenced
- Gate: `scripts/qc.py`, `scripts/validate_references.py`
- Schema / enums: `src/drugmechdb/schema/drugmechdb.yaml` (`EvidenceSupportEnum`, `EvidenceSourceEnum`)
- Saturation evidence: `docs/phase3_model_comparison.md`
- Worked failure: `tests/phase3_eval_outputs/P06.yaml`
- Keepability conventions: `.claude/skills/dmdb-compliance/SKILL.md`, `CurationGuide.md`
