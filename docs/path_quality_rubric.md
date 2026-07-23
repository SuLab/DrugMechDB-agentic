# Path-Quality Rubric (decomposed, edge-by-edge)

> **What this is.** The single **scored checklist** for judging whether a curated path is *good* —
> the one rubric the **semantic critic** (`scripts/quality/critic.py`), the **LLM judge**
> (`scripts/quality/prompts/edge_evidence_judge.md`, `path_coherence_judge.md`), and **human
> review** all score against, so they cannot drift apart.
>
> **What this is *not*.** It is not the argument for *why* these criteria are the right ones, nor
> the measurement architecture — that is `docs/path_quality_framework.md` (§3 the edge ladder, §4
> path validity, §5 gold agreement, §6 grounding, §7 calibration). This doc is the operational
> distillation of that framework: *what to score*, not *why*. When the two conflict, the framework
> is authoritative and this checklist is wrong and must be fixed.
>
> **Where it sits.** Everything here is *above* the syntactic QC floor (`scripts/qc.py` Layers 1–4:
> schema, node ontology, predicate enum, verbatim snippet). QC answers "is this well-formed?"; this
> rubric answers "is it *true / the mechanism*?" — the blind spot the gate cannot see.

---

## How to score

- **Edge checks** (§A) use `pass` / `partial` / `fail` / `abstain`, each with a **cited basis**
  (the retrieved span or database record it rests on). `abstain` when a check cannot be grounded —
  never guess. Abstain routes the edge to a human.
- **Per-edge verdict** rolls the checks up into the schema's `EvidenceSupportEnum`
  (`SUPPORT` / `PARTIAL` / `NO_EVIDENCE` / `REFUTE` / `WRONG_STATEMENT`), **re-derived
  independently** of the curator's self-assigned label. Disagreement with the curator is a
  *finding*, not an error to avoid.
- **Path judgments** (§B) each produce a verdict + cited basis + confidence, or `abstain`.
- **Overall verdict** ∈ `accept` / `revise` / `reject` / `abstain`.
- **The keep/reject threshold and component weighting are a maintainer decision** (issue #10) — this
  rubric produces the *profile*; it does not collapse quality to one number or bake in a cutoff.

**Grounding rule (applies to every criterion).** Ground each judgment in retrieved text or an
independent authority — **never in the scorer's own parametric memory** — and cite the exact span
or record. A load-bearing judgment must rest on a source the curator did **not** cite (ChEMBL
`get_mechanism`, or a paper retrieved independently). If nothing independent can ground it,
`abstain`. (Framework §6.)

---

## A. Per-edge criteria — the atomic faithfulness ladder

An edge is a triple `(subject_CURIE, predicate, object_CURIE)` + a `snippet` + a `reference`. Run
**every** check on **every** evidence item. (Framework §3; operationalized by
`edge_evidence_judge.md`.)

| # | Check | Question | `fail` / `partial` looks like |
|---|-------|----------|-------------------------------|
| 1 | **verbatim** | Is the snippet an exact substring of the cited source? (QC Layer 4 already enforces this — re-confirm + read the surrounding sentence for context.) | not present verbatim |
| 2 | **subject grounding** | Does the snippet (or an independent source) assert something about the edge's **subject** entity specifically? | a metabolite, parent compound, salt form, or class member of the subject → a *different* entity |
| 3 | **object grounding** | Is the edge's **object** the thing the relation *acts on* — not merely co-mentioned or downstream? | a downstream readout, or a co-mentioned entity that isn't the target |
| 4 | **polarity** | Does the snippet's relation direction (increase / decrease / no-change) match the predicate's sign? | source says "increases", edge says `decreases …` |
| 5 | **direction** | Does the subject act on the object (not the reverse)? | object acts on subject |
| 6 | **granularity** | Is this the right *flavor* — activity vs abundance vs expression vs binding? | "inhibits activity" cited for a `decreases abundance of` edge |
| 7 | **scope / modality** | Does the source *assert the mechanism as established*, or is it hedged ("may", "we hypothesize") or bound to one cell line / species / dose the edge over-generalizes? | a hedged or narrow-context sentence read as a general assertion |
| 8 | **source-type** | Is `evidence_source` accurate for the publication's methodology (clinical / model-organism / in-vitro / computational / review)? | `IN_VITRO` on a definitional review sentence |

**Per-edge verdict (re-derived `EvidenceSupportEnum`):**

| Verdict | When |
|---------|------|
| `SUPPORT` | subject / object / polarity / direction / granularity all pass; scope adequate |
| `PARTIAL` | substantively right, real gap (e.g. about a metabolite of the subject; right entities but a downstream readout; narrow scope over-generalized) |
| `NO_EVIDENCE` | verbatim and maybe on-topic, but does not establish *this* edge (e.g. a snippet reused for an edge it doesn't speak to) |
| `REFUTE` | the source contradicts the edge (opposite sign / direction) — **escalate to human** |
| `WRONG_STATEMENT` | the edge contains a factual error the source corrects — **escalate to human** |

Keep **`edge_supported`** (is the edge itself defensible, possibly via independent grounding even
when the *cited* snippet is weak?) separate from the per-snippet verdict: an edge can be true while
its citation is bad (fixable — re-source) or false regardless of citation (must change — escalate).

---

## B. Per-path criteria — edge-evidence ≠ path-truth

A path of individually-supported edges can still fail to be *the mechanism*. Judge the chain as a
whole. (Framework §4; operationalized by `path_coherence_judge.md`.)

| Criterion | Question | Deterministic? |
|-----------|----------|----------------|
| **net polarity** | Collapse the path to its signed backbone; walking drug→disease, the product **must be negative** (the disease ends up decreased). | **Yes** — sign table over the 67 predicates. Highest-leverage objective check. |
| **parsimony / no shortcut** | Is it a *single* connected chain, or does it also carry a redundant **shortcut/bypass** edge — a direct `Drug —treats→ Disease` (or other clinical-outcome) edge on top of a worked-out mechanism, or a jump to an already-reached node? Such an edge restates the conclusion even when its *fact* is true. The single-link `Drug —treats→ Disease` stub is valid **only** as the entire path. | Mostly — flag any edge whose removal leaves the path connected + net-negative |
| **topology convention** | Starts `Drug → Protein target`; ~3–7 links; branch **only** where actions converge. | Mostly scriptable |
| **mechanism is accepted** | Does an independent authority describe *this* chain (or a clearly equivalent one) as the drug's MoA for this indication? | No — model + independent grounding |
| **is primary MoA** | Is this the *principal* mechanism for the indication, not a secondary/incidental effect? | No |
| **wrong intermediate** | Is a step present but not on the accepted causal route? | No |
| **coverage / missing step** | Is a critical intermediate absent? (A path that is all-positive to a disease the drug treats usually means a **sign-flipping step was omitted**.) *The genuinely hard one — cannot be made objective without a reference path or pathway oracle; stays human-anchored.* | No — residual (Framework §8) |

**Firewall for the agent-facing flag.** For evidence/coverage findings, tell the curator *what* is
wrong (the symptom and the implicated region) and **never** the fix, the specific missing entity, a
PMID, or a source — the curator must re-derive independently. **Exception:** a shortcut/bypass edge
is a *structural* redundancy, not a scientific spoiler, so name the offending edge and say to remove
it.

---

## C. Sourcing appropriateness

- **Source-agnostic** (decided 2026-07): evidence may come from any connected source that *asserts*
  the established mechanism (PubMed, preprint servers, ChEMBL, clinical trials,
  reviews, well-sourced references). No predicted/model-generated mechanism is ever a curation
  input.
- The `EvidenceItem.snippet` must be a **verbatim** substring of the fetched source.
- **Ephemeral full text:** anything beyond an abstract is fetched only to extract + verify the
  snippet and its citation, then deleted after QC — the committed repo keeps the snippet + citation,
  never the copyrighted body.

*(A verifier may *read* broader sources — including primary literature — to check a claim; the
conservative-sourcing boundary constrains the curator's **inputs**, not the checker's **evidence**.
Framework §6a.)*

---

## D. Gold-path agreement (in-corpus pairs only)

When the pair has a `legacy_path_id`, an expert path already exists, so agreement is measurable —
with two non-negotiable cautions (Framework §5):

- **Compare semantically, not by exact CURIE/predicate match** — normalize entities and compare
  predicates *up to Biolink-version translation*, so vocabulary drift does not register as a quality
  disagreement.
- **Disagreement ≠ error.** Classify the relationship: `reproduces` / `agent_more_complete` /
  `agent_simpler_but_valid` / `disagree`. The distribution of these labels *is* the evidence for the
  forwardfill-vs-keep decision — not a per-path pass/fail.

---

## Aggregate verdict

| Verdict | Meaning |
|---------|---------|
| `accept` | edges faithful, path valid, no hard-gate failure |
| `revise` | at least one `PARTIAL`/`NO_EVIDENCE` edge, a missing/wrong step, or a shortcut edge — loop back to curation |
| `reject` | a hard-gate failure (net polarity wrong after review, disconnected, `REFUTE`/`WRONG_STATEMENT`) |
| `abstain` | a load-bearing judgment could not be independently grounded — route to human |

**Calibration (why any of this is defensible).** Until a judgment's Cohen's κ vs a blinded ≥2-rater
human sample clears threshold (Framework §7), the LLM judge **proposes** and a human **disposes** on
that judgment. Auto-trust the judge only per-sub-check, where it has cleared calibration; `coverage`
and `mechanism_is_accepted` are expected to stay human-anchored longest.

---

## Consumers of this rubric

| Consumer | How it uses the rubric |
|----------|------------------------|
| `scripts/quality/critic.py` | orchestrates the edge + path judges and the structural report against these criteria in-session |
| `scripts/quality/prompts/edge_evidence_judge.md` | operationalizes §A (the atomic ladder) for the LLM edge judge |
| `scripts/quality/prompts/path_coherence_judge.md` | operationalizes §B (path validity) for the LLM path judge |
| Human-review protocol (issue #12) | uses this as the blinded-review scoring guide |

### See also
- `docs/path_quality_framework.md` — the design rationale + measurement architecture (authoritative).
- `docs/quality_system_design.md` — the issue taxonomy (E1–E5) these criteria detect.
- `src/drugmechdb/schema/drugmechdb.yaml` — `EvidenceSupportEnum`, `EvidenceSourceEnum`.
- Issue #10 — the keep/reject threshold + component weighting (the maintainer decision this rubric feeds).
