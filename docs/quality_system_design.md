# Post-QC Quality System — Design, Issue Taxonomy & Reliability

> **Status:** design doc. Companion to `docs/path_quality_framework.md` (the *why*);
> this is the *what / how reliable / what's still missing*. Reflects the deterministic
> checker as built in `scripts/quality/` and measured on the 4,846-record corpus.
>
> The LLM judge layer (§4) is **built and wired**, not just prompt specs:
> grounding tools + agentic tool-loop backends + both judge runners + a single orchestrator
> (`scripts/quality/quality_profile.py`) that merges QC + structural + semantic into one
> profile. See §4 and `scripts/quality/judge/README.md`. The remaining gate is **calibration**
> (§ Reliability / framework §7), not construction.

---

## 1. The funnel — why no single layer is "airtight," but the stack can be

"Weed out ~98% of issues" is **not** achievable by any one mechanism, because path quality
spans two fundamentally different kinds of defect:

- **Structural / formal defects** — graph shape, sign logic, predicate-type fit, metadata
  consistency. These are *decidable from the record alone* → **deterministic code**, cheap,
  high precision, no calibration.
- **Semantic defects** — does this snippet establish this edge? is this the accepted mechanism?
  is a step missing? These require *reading external sources* → **LLM judge** (grounded,
  calibrated) + **human** for the residual.

So the system is a **funnel**, and "airtight" is defined operationally as: **every issue class
in §3 has a named detector and a characterized miss-rate.** Efficiency comes from ordering the
funnel cheap→expensive: the deterministic layer runs on the whole corpus in ~9 s at $0 and
HARD-clears **87.8%** of records, so the expensive LLM judge only spends tokens on (a) the
evidence-semantic checks it alone can do, and (b) the prioritized residual the cheap layer flags.

```
  Layer 1-4 QC gate ──► Deterministic structural (§2) ──► LLM evidence/mechanism judge (§4) ──► Human adjudication
  (well-formedness)      (~9s, $0, 87.8% HARD-clean)        (grounded, calibrated, $/path)        (coverage, gold, novelty)
```

---

## 2. The deterministic layer (built: `scripts/quality/structural_quality.py`)

Severity tiers: **HARD** = a logical error a correct mechanism cannot have (act on these);
**SOFT** = convention/prioritization (review); **INFO** = note. Net-polarity is computed over
**all** drug→disease simple paths and classified `coherent / incoherent (all branches net +) /
inconsistent (branches disagree) / indeterminate (reverse/opaque predicate — not composed)`.

### Corpus result (4,846 records)

| Metric | Value |
|---|---|
| Fully clean (no flags) | 1,824 (37.6%) |
| **HARD-clean (no logical error)** | **4,254 (87.8%)** |
| ≥1 HARD flag | 592 (12.2%) |
| polarity coherent / indeterminate / incoherent / inconsistent | 4,300 / 444 / 65 / 37 |

| Flag (code) | Sev | Count | Reliability (evidence-based) |
|---|---|---|---|
| `length_out_of_range` | SOFT | 1,583 | heuristic only — **not** an error detector; prioritization |
| `noncanonical_start` | INFO | 1,008 | first target ≠ Protein; **allowed** (chelators, prodrugs) — note only |
| `review_predicate` | INFO | 884 | polarity leaned on a `review`-confidence sign → ratify lexicon |
| `type_violation` | HARD | 445 | **medium-high precision**; conservative-but-strict; ratify constraints |
| `net_polarity` (indeterminate) | SOFT | 444 | reverse/opaque predicate — honestly *can't* decide → route on |
| `net_polarity` (incoherent+inconsistent) | HARD | 102 | **high precision** (3/3 sampled were real: sign errors + a missing sign-flip step) |
| `direct_drug_disease` | HARD | 91 | high precision (drug's only target is the disease) |
| `short_circuit` | HARD | 60 | high precision after restricting to ≤2-edge bypasses |
| `duplicate_edge` | HARD | 44 | exact — identical (s,t,key) repeated |
| `clinical_shortcut` | HARD | 2 | exact |
| `cycle` | HARD | 1 | exact — paths must be acyclic |

### Reliability summary (what changed from v1, and why to trust v2)

- **Net-polarity is now reliable.** v1 picked one arbitrary path → false positives (P10) and
  silently miscomputed reverse predicates. v2 evaluates **all** paths, routes reverse/opaque
  predicates to `indeterminate` instead of guessing, and distinguishes `incoherent` from
  `inconsistent`. Validated: P06 → `coherent` (issue correctly isolated to the `treats`
  short-circuit); P10 → `inconsistent`; sampled `incoherent` records were all genuine
  (Hep-C sign error; Goserelin missing desensitization step).
- **`short_circuit` false positives removed** (814 → 60) by only flagging ≤2-edge bypasses;
  longer parallel branches are legitimate **convergence**, not shortcuts.
- **`type_violation` is new and conservative.** It only fires when both endpoint types are known
  and a constraint is violated. Constraints err strict (e.g. "decreases activity of" excludes
  ChemicalSubstance). Treat the 445 as *high-value review*, not certain errors, until ratified.
- **Soft/Info vs Hard separation is the key reliability move.** The 12.2% HARD set is the
  high-precision actionable bucket; length/start/indeterminate are explicitly *not* claimed as errors.

### Known residual false-positive modes (be honest)
- `type_violation`: legitimate-but-loose predicate usage the constraints don't allow yet.
- `short_circuit`: a genuine 2-edge convergent branch beside a longer one can trip it.
- `net_polarity` depends on the lexicon; `review`-confidence signs (884 records) are unratified.

---

## 3. The complete issue taxonomy → detector matrix ("all possible issues")

Owner: **det** = deterministic code · **LLM** = grounded judge (§4) · **gold** = compare to legacy
path · **human** = adjudication. Status: ✅ built · 🟡 partial · ⬜ planned.

### A. Graph / structure — **det**
| | Issue | Detector | Sev | Status |
|---|---|---|---|---|
| A1 | malformed graph | Layer 1 schema | gate | ✅ |
| A2 | no drug→disease path | `connectivity` | HARD | ✅ |
| A3 | directed cycle | `cycle` | HARD | ✅ |
| A4 | duplicate edge | `duplicate_edge` | HARD | ✅ |
| A5 | dangling node | `dangling_node` | SOFT | ✅ |
| A6 | net-polarity incoherent/inconsistent | `net_polarity` | HARD | ✅ |
| A7 | short-circuit / clinical bypass | `short_circuit`,`clinical_shortcut` | HARD | ✅ |
| A8 | direct drug→disease | `direct_drug_disease` | HARD | ✅ |
| A9 | length out of 3–7 | `length_out_of_range` | SOFT | ✅ |
| A10 | non-canonical start | `noncanonical_start` | INFO | ✅ |
| A11 | non-convergent branching | (part of short_circuit) | SOFT | 🟡 |

### B. Node / entity — **det + ontology, some LLM**
| | Issue | Detector | Sev | Status |
|---|---|---|---|---|
| B1 | non-existent CURIE | Layer 2 (OAK) | gate | ✅ |
| B2 | prefix↔type mismatch | Layer 2 | gate | ✅ |
| B3 | name drift (label ≠ canonical) | Layer 2 | SOFT | 🟡 |
| B4 | wrong Biolink type for entity | OAK + LLM | — | ⬜ |
| B5 | wrong granularity (gene vs protein vs complex) | OAK + LLM | — | ⬜ |

### C. Predicate — **det + LLM**
| | Issue | Detector | Sev | Status |
|---|---|---|---|---|
| C1 | not in 67-enum | Layer 3 | gate | ✅ |
| C2 | predicate↔node-type (domain/range) | `type_violation` | HARD | ✅ |
| C3 | sign wrong vs the actual biology | LLM (evidence) | — | ⬜ (prompt) |
| C4 | direction reversed (`caused by` vs `causes`) | det (→ indeterminate) + LLM | — | 🟡 |
| C5 | too coarse (`regulates`) | det (→ opaque flag) + LLM | — | 🟡 |

### D. Evidence (per-edge) — **LLM + verification** (the heart of §4)
| | Issue | Detector | Sev | Status |
|---|---|---|---|---|
| D1 | snippet not verbatim | Layer 4 | gate | ✅ |
| D2 | snippet **subject** ≠ edge subject (P06 endoxifen) | LLM judge | — | ⬜ (prompt) |
| D3 | snippet **object** ≠ edge object (P10 HER2/PI3K) | LLM judge | — | ⬜ (prompt) |
| D4 | snippet **relation** ≠ predicate (polarity/dir/gran) | LLM judge | — | ⬜ (prompt) |
| D5 | scope/modality mismatch (hedged, wrong context) | LLM judge | — | ⬜ (prompt) |
| D6 | wrong `supports` label (self-graded SUPPORT) | LLM judge re-derives | — | ⬜ (prompt) |
| D7 | wrong `evidence_source` label | LLM judge | — | ⬜ (prompt) |
| D8 | source-type policy violation (primary lit) | det(meta) + LLM | — | 🟡 |
| D9 | **same snippet reused across distinct edges** (P06 edge 3) | **det (cheap!)** | SOFT | ⬜ next |
| D10 | citation/PMID doesn't exist | det (fetch) | — | 🟡 |

### E. Path-mechanism — **LLM + gold + human**
| | Issue | Detector | Sev | Status |
|---|---|---|---|---|
| E1 | edges supported but chain ≠ accepted MoA | LLM + gold | — | ⬜ (prompt) |
| E2 | **missing critical step** (coverage) | LLM + gold + human; *sign-flip subset caught by A6* | — | 🟡 |
| E3 | wrong intermediate | LLM + gold | — | ⬜ |
| E4 | disagreement with gold path | det graph-compare + human adjudication | — | ⬜ |
| E5 | not the *primary* MoA for this indication | LLM + human | — | ⬜ |

### F. Metadata — **det (cheap wins remaining)**
| | Issue | Detector | Sev | Status |
|---|---|---|---|---|
| F1 | `_id` ≠ filename / format | det | — | ⬜ next |
| F2 | drug/disease MeSH ≠ graph fields | det | — | ⬜ next |
| F3 | references missing/malformed | Layer 1 / refs | gate | 🟡 |
| F4 | drug node ≠ the indication's drug | det | — | ⬜ next |

**Immediate cheap deterministic wins still on the table:** D9 (evidence-reuse — trivial, was a real
P06 defect), F1/F2/F4 (id/mesh consistency), A11. Building these pushes the deterministic layer to
its coverage ceiling before any LLM spend.

---

## 4. The LLM judge layer (BUILT — `scripts/quality/judge/`)

Everything in **D2–D8, C3–C5, E1/E3** is semantic and needs a grounded LLM. The prompts are
concrete artifacts in `scripts/quality/prompts/`:
- `edge_evidence_judge.md` — runs the atomic faithfulness ladder per evidence item, re-derives
  the `EvidenceSupportEnum` value, emits per-check booleans (for calibration) + cited grounding.
- `path_coherence_judge.md` — judges the chain as a whole (accepted MoA, missing step, primacy).

**These prompts are now executed by a runnable harness** (was: "next integration step"). The
package layout:
- `judge/grounding.py` — the external referents the judge must cite (framework §6): `read_source`
  (cited PMID text + snippet context, via the `pubmed_fetch` wrapper — tier 3) and
  `chembl_get_mechanism` (ChEMBL drug→target→action — tier 1; resolves salt/parent forms).
  Deterministic, cached, never raises.
- `judge/backends.py` — a provider-agnostic agentic **tool-loop**: `AnthropicBackend`,
  `OpenAIBackend`, and a `StubBackend` (so the whole pipeline runs offline, no key).
- `judge/runner.py` — loads a prompt's SYSTEM section, drives the loop, robustly parses the JSON
  verdict, caches verdicts (`quality_cache/verdicts/`).
- `judge/edge_evidence_judge.py` / `judge/path_coherence_judge.py` — build the prompt-spec input
  from a path YAML and return structured verdicts.
- `scripts/quality/quality_profile.py` — the orchestrator: QC gate + `structural_quality.analyze`
  + the two judges → one merged profile (`hard_gates`, `edge_faithfulness`, `path_coherence`,
  `overall`). Run via `just quality-profile <file>` (`--no-llm` for deterministic-only).

The judge is chosen to be a **different model family than the curator** for independence
(`make_backend`: prefer OpenAI vs the Claude curator; configurable via `DMDB_JUDGE_PROVIDER` /
`DMDB_JUDGE_MODEL`). Without an API key the deterministic profile is still produced and the
semantic section is marked `not_run` — so the layer degrades cleanly. The taxonomy statuses for
**D2–D8, C3–C5, E1–E5** are therefore now *wired (🟡 pending calibration)* rather than ⬜.

**Non-negotiable design rules baked into the prompts** (from `path_quality_framework.md` §6):
1. **Grounding, not memory** — verdicts must rest on retrieved source text or an independent DB
   (ChEMBL `get_mechanism`, OAK, PubMed), never the model's parametric belief.
2. **Cite-or-abstain** — every verdict cites the span/record it used; if it can't ground, it
   returns `ABSTAIN` → human, never a guess.
3. **Ignore the curator's self-labels** — re-derive `supports`/`evidence_source` independently.
4. **Different model family** than the curator (cheap independence).
5. **Structured JSON output** the deterministic harness can ingest → the two layers merge into
   one quality profile per record.

**Calibration is the gate on trusting the LLM** (§7 of the framework): score a blinded ≥2-rater
human sample, compute Cohen's κ **per sub-check**, and auto-trust the judge only where κ clears
threshold. The deterministic checks above double as **free calibration anchors** — e.g. the judge's
view of an edge's polarity must agree with the lexicon's net-polarity computation.

---

## 5. Can it hit 98%?

Honest decomposition: the deterministic layer gives **high precision** on classes A, C2, F (and the
sign/coverage subset of A6/E2) — that's where structural errors concentrate (12.2% HARD set). The
**majority of evidence-level defects (D2–D8) are invisible to it** and are the LLM judge's job; the
chain-level residual (E2 full coverage, E4/E5) needs gold + human. So **98% is a property of the
*funnel*, contingent on the LLM judge being calibrated to adequate recall** — not a claim any single
layer can make. The deterministic layer's contribution to that 98% is being the cheap, high-precision
pre-filter that makes the expensive recall affordable.
