# Biolink + Ontology Drift Audit — Legacy DrugMechDB Corpus

**Scope:** READ-ONLY (measurement only; no fixes applied)
**Corpus:** 4,846 path files in `kb/paths/` · 33,009 node occurrences (5,128 unique CURIEs) · 32,641 edges
**Reference models:** Biolink Model **4.2.2** (via `bmt` 1.4.8 / `biolink-model` 4.4.2); OBO ontologies via OAK `sqlite:obo:` adapters + EBI OLS4.

> **Why this exists.** DrugMechDB was built on Biolink **v1.3.0 (~2021)**. The maintainers suspected the legacy predicates and
> node IDs/names had drifted or been deprecated since. They have — substantially. The two in-repo "all-green" checks
> are not evidence of validity: Layer-3 predicate validation is **circular** (its 67-member enum was *derived from this
> corpus*, see `phase1_5_predicate_canonicalization.md`), and the deep node check (`--deep`) had **never been run**
> (`phase2_gap_report.md`). This audit runs the real checks against external authorities.

---

## 1. Summary

### Predicates (Biolink 4.2.2) — the headline

| Metric | Count | % of 67 | Edge-weighted (of 32,641) |
|---|---:|---:|---:|
| **Current** in Biolink 4.2.2 | 46 | 68.7% | 15,770 (48.3%) |
| **Not in** Biolink 4.2.2 (removed) | **18** | **26.9%** | **16,812 (51.5%)** |
| **Renamed** (slot exists under a new IRI) | 3 | 4.5% | 59 (0.2%) |

**Over half of all edges in the corpus (51.5%) use a predicate that no longer exists in current Biolink** — including
the five most-used predicates in the entire database. These were valid in v1.3.0 and were removed in Biolink's
"qualifier" refactor (v2→v3, ~2022).

### Nodes

| | Unique IDs | Node occurrences |
|---|---:|---:|
| Total in corpus | 5,128 | 33,009 |
| **Authoritatively deep-checked** (OAK/OLS, every ID) | **1,514 (29.5%)** | **12,778 (38.7%)** |
| Spot-checked only (sample) — MESH, UniProt, DB | 348 sampled of 3,413 | — |
| **Not verifiable / not verified** (InterPro, Pfam, reactome, TIGR) | 201 (3.9%) | 1,323 (4.0%) |

Of the **1,514** IDs deep-checked against OBO authorities:

| Result | Unique IDs | % | Occurrences |
|---|---:|---:|---:|
| Active & current | 1,470 | 97.1% | 12,648 |
| **Obsolete / deprecated** | **40** | **2.6%** | 99 |
| **Unresolvable** (ID not in ontology) | **4** | **0.3%** | 31 |
| — of the active, **substantive label drift** | 100 | 6.6% | 296 |
| — of the active, cosmetic label drift | 14 | 0.9% | — |

> **The node numbers look reassuring only because MeSH — the single largest prefix (49.5% of all unique IDs) — cannot
> be checked by OAK at all.** See §4. Do not read "2.6% obsolete" as a corpus-wide figure; it is a figure for the
> ~30% of IDs that live in OBO ontologies.

---

## 2. Task A — Node ontology drift

`--deep` (which delegates to `linkml-term-validator … --lenient`) is **not reachable through `qc.py`** — `qc.py`'s
Layer-2 call never passes `--deep`; it must be invoked directly on the layer script. The `--deep` toolchain was
smoke-tested on 5 records (runs end-to-end, exit 0). For deterministic, parseable, **per-node + per-prefix** results
with explicit coverage accounting — and because `linkml-term-validator` cannot resolve the non-OBO prefixes either —
the audit was driven directly via OAK (`oaklib`, offline SQLite) and OLS4, classifying each ID as
**active / obsolete / unresolvable** with `owl:deprecated` + `IAO:0100001` (term-replaced-by) metadata, plus label-drift.

### 2a. Obsolete / deprecated terms — 40 (GO 37, HP 2, CHEBI 1)

OBO terms flagged `owl:deprecated` or carrying an `obsolete …` canonical label. Examples (uses × in corpus):

| ID | Uses | Stored name | Replaced by |
|---|---:|---|---|
| GO:0046323 | 14 | Glucose import | GO:0098708 |
| GO:0016575 | 12 | Histone deacetylation | (no successor) |
| GO:0140603 | 5 | ATP hydrolysis activity | GO:0016887 |
| GO:0045272 | 5 | plasma membrane respiratory chain complex I | GO:0045271 |
| GO:0001207 | 7 | histone displacement | (no successor) |
| CHEBI:21241 | 1 | vitamin C | CHEBI:176783 |
| HP:0002355 | — | Difficulty walking | (obsolete) |

A meaningful share have **no replacement term** (`replaced_by`/`consider` empty) — those edges cannot be silently
remapped; they require re-curation.

### 2b. Unresolvable IDs — 4

| ID | Uses | Stored name | Note |
|---|---:|---|---|
| taxonomy:11103 | 21 | Hepacivirus C | NCBITaxon 404 (merged/retired taxid) |
| taxonomy:1535326 | 7 | Candida | NCBITaxon 404 |
| taxonomy:5519 | 2 | Malassezia | NCBITaxon 404 |
| GO:005507 | 1 | iron ion homeostasis | **malformed ID** — 6 digits; almost certainly a typo of the (now-obsolete) GO:0055072 |

### 2c. Substantive label drift — 100 active terms (296 occurrences)

The stored `name` differs from the current canonical label by more than punctuation/case/Greek-letter formatting.
This bucket is conservative — it includes harmless word-order changes **and** genuinely wrong mappings. The concerning
subset is where the stored name names a *different concept* than the term now denotes:

| ID | Uses | Stored name | Current canonical label |
|---|---:|---|---|
| GO:0004697 | — | Protein kinase C activity | diacylglycerol-dependent serine/threonine kinase activity |
| GO:0003676 | — | bacterial Nucleic Acid synthesis | nucleic acid binding |
| GO:0002154 | 11 | Thyroid hormone mediated signaling pathway | thyroid hormone receptor signaling pathway |
| GO:0004484 | — | mRNA capping enzyme activity | mRNA guanylyltransferase activity |
| taxonomy:2104 | 21 | Mycoplasma pneumoniae | Mycoplasmoides pneumoniae *(genus reclassified)* |
| taxonomy:1872 | — | **Bacillus anthracis** | **Actinoplanes sp. ATCC 31351** *(ID now denotes a different organism — likely wrong taxid)* |
| UBERON:0035501 | 8 | Free nerve ending | unencapsulated tactile receptor |

Plus 14 **cosmetic** drift cases (mostly CHEBI Greek-letter vs ASCII: `α`→`alpha`, `→`→`->`, plurals) — not errors,
but they will trip exact-label validators.

### 2d. Secondary/merged accessions

The taxonomy 404s (2b) and the 3 inactive UniProt accessions (§4) are merged/demerged secondary IDs — they once
resolved but are no longer primary. Captured under unresolvable/inactive rather than as a separate bucket.

---

## 3. Task B — Predicate drift (against real Biolink 4.2.2)

Validated each of the 67 enum predicates against the pinned Biolink Model via `bmt`, resolving by label, by the
underscored `meaning:` slot, and by CURIE. **The circular Layer-3 validator was deliberately not used.**

### 3a. Not in Biolink 4.2.2 — 18 predicates (16,812 edges, 51.5%)

These were valid in v1.3.0 and were removed when Biolink moved activity/abundance/regulation/expression relations into
the **qualifier model** (the replacements now exist as e.g. *"increases amount or activity of" / "decreases amount or
activity of"*, or `affects` + `object_aspect_qualifier` / `object_direction_qualifier`):

| Predicate | Uses | Predicate | Uses |
|---|---:|---|---:|
| positively regulates | **6,630** | decreases abundance of | 476 |
| decreases activity of | **4,561** | molecularly interacts with | 109 |
| increases activity of | **1,974** | affects risk for | 82 |
| negatively regulates | **1,913** | increases degradation of | 9 |
| increases abundance of | 1,028 | contraindicated for | 8 |
| | | increases transport of | 7 |
| | | directly interacts with | 5 |
| | | increases stability of | 4 |
| | | decreases synthesis of | 2 |
| | | increases/decreases expression of, predisposes, decreases uptake of | 1 each |

### 3b. Renamed — 3 predicates (59 edges)

The bare verb was replaced by an `…_condition` slot:

| Enum label | Enum `meaning:` | Current Biolink slot |
|---|---|---|
| prevents | biolink:prevents | **biolink:preventative_for_condition** |
| ameliorates | biolink:ameliorates | **biolink:ameliorates_condition** |
| exacerbates | *(none — enum already self-flags it non-standard)* | **biolink:exacerbates_condition** |

### 3c. Enum-meaning integrity

For all 46 "current" predicates the enum's `meaning:` CURIE matches the live Biolink `slot_uri`, and every resolved
element `is_predicate` (descends from `related to`) — no mis-typed (non-predicate) entries were found. The integrity
problem is **absence/rename**, not wrong-IRI-mapping (except the 3 in 3b and the 18 in 3a whose `meaning:` IRIs now
dangle).

### 3d. v1.3.0 comparison

The audit pins **v4.2.2** as "current." A programmatic v1.3.0 load was **not run** (would require fetching a legacy
remote schema). Analytically: all 18 "not in 4.2.2" predicates *did* exist in v1.3.0 — DrugMechDB was built on it — so
this table *is* the v1.3.0→v4.2.2 delta for the predicates the corpus uses. The drift is real, not a tooling artifact.

---

## 4. Coverage caveats — what was NOT checked (read this before trusting §1)

OAK's `sqlite:obo:` adapters cover **only OBO ontologies**. DrugMechDB is dominated by **non-OBO** identifiers that OAK
cannot resolve. Silence on these is **not** validity.

| Prefix | Unique IDs | Occurrences | Verification | Result |
|---|---:|---:|---|---|
| **MESH** | **2,539 (49.5%)** | 11,633 | NLM MeSH, **sample 150** | 150/150 resolve; **label drift NOT assessed** |
| **UniProt** | 776 | 7,055 | UniProt REST, **sample 100** | 97 active, **3 inactive (~3%)** (merged TrEMBL accs) |
| GO/HP/CL/UBERON/CHEBI/PR | 1,348 | 11,431 | OAK + OLS, **full** | see §2 |
| **taxonomy → NCBITaxon** | 166 | 1,347 | OLS4, **full** | 163 active, 3 unresolvable, 18 reclassified |
| **DB (DrugBank)** | 98 | 220 | MyChem, **all 98** | 93 indexed, **5 not indexed** — all `DBMET…`/`DBSALT…` (metabolite/salt sub-IDs, a non-standard ID class) |
| **InterPro** | 103 | 879 | **NOT verified** | counts only |
| **reactome** | 81 | 329 | **NOT verified** | counts only (also a legacy prefix; canonical is `REACT`) |
| **Pfam** | 16 | 112 | **NOT verified** | counts only (legacy prefix) |
| **TIGR** | 1 | 3 | **NOT verified** | counts only (legacy prefix) |

Concretely: **MeSH label drift is completely unassessed**, and **InterPro/Pfam/reactome/TIGR (201 unique IDs / 1,323
occurrences) were not validated at all.** A future pass should resolve MeSH labels (UMLS/NLM), InterPro/Pfam (EBI APIs),
and Reactome (Reactome ContentService) to close the ~70% of unique IDs this audit could only spot-check or tabulate.

> **➡ This gap is now closed — see the companion report [`mesh_node_drift_report.md`](mesh_node_drift_report.md)**
> (+ [`drift_audit_mesh.json`](drift_audit_mesh.json)). It resolves every non-OBO ID against its own authority, taking
> node-layer coverage from 29.5% → **99.9%**. Headline: the node IDs are largely sound (~89% resolve + current + name-OK;
> only ~3.5% have a hard validity problem — notably 93 retired MeSH **drug** SCRs; MeSH **disease** IDs are 100% current),
> and the apparent name drift is mostly benign labeling — the opposite of the predicate finding below.

This audit also **does not** re-litigate the 230 prefix violations + 1,768 legacy-prefix warnings already documented in
`phase2_gap_report.md` (those are prefix↔label mismatches; this audit is about *term validity* given the stored ID).

---

## 5. Recommended follow-ups (NOT applied — measurement only)

1. **Predicate remap is the dominant work item.** 51.5% of edges use removed predicates. Decide the target Biolink
   version (the v1.3.0-vs-v4.x question this audit forces) and build a **qualifier-aware** mapping
   (`positively regulates`→`regulates`+direction qualifier; `decreases activity of`→`affects`+aspect/direction; etc.).
   This is not a lexical rename — it changes the edge model. **This single decision dominates whether to backfill legacy paths or re-curate them.**
2. **Re-curate the 40 obsolete + 4 unresolvable terms**; those with no `replaced_by` cannot be auto-migrated. Fix the
   malformed `GO:005507` and the wrong `taxonomy:1872` (Bacillus anthracis) ID.
3. **Triage the 100 substantive-drift terms**; separate harmless word-order/qualifier reorderings from genuinely-wrong
   mappings (e.g., `GO:0004697` "Protein kinase C", `GO:0003676`).
4. **Close the coverage gap**: validate MeSH labels, UniProt (full), InterPro/Pfam/Reactome via their authorities.
5. **Replace the circular Layer-3 check** with a real Biolink-Model-backed validator (pin a version; add `bmt` as a dep).
6. **Wire `--deep` + a `bmt` predicate check into CI** (Phase 4) with adapter caching (note the disk cost — NCBITaxon's
   local SQLite is ~8 GB; prefer OLS HTTP for taxon/PR).

---

## 6. Reproducibility

Deterministic; all remote calls cached under `audit_work/{ols_cache,nonobo_cache}/`. Machine-readable outputs:
`docs/drift_audit_nodes.json`, `docs/drift_audit_predicates.json`.

```bash
# env (one-time): pip install -e ".[dev]" ; pip install bmt
# macOS framework-Python TLS gotcha — point OpenSSL at certifi or downloads fail:
export SSL_CERT_FILE="$(.venv-py310/bin/python -c 'import certifi; print(certifi.where())')"

python audit_work/inventory.py                              # node inventory + per-prefix coverage
python audit_work/oak_check.py GO HP CL UBERON CHEBI        # OBO deep check (OAK, offline SQLite)
python audit_work/ols_check.py taxonomy ncbitaxon NCBITaxon # NCBITaxon via OLS4 (avoids 8 GB local DB)
python audit_work/ols_check.py PR pr PR
python audit_work/nonobo_spotcheck.py                       # MESH/UniProt/DB sampled, cached
python audit_work/predicate_audit.py                        # 67 predicates vs Biolink 4.2.2 (bmt)
python audit_work/aggregate_nodes.py                        # -> docs/drift_audit_nodes.json
```

Disk note: OAK downloads SQLite ontologies to `~/.data/oaklib/` (GO/CHEBI/UBERON each ~1–4 GB; NCBITaxon ~8 GB). Delete
`*.db.gz` after extraction to reclaim space; this audit used OLS HTTP for NCBITaxon/PR to avoid the largest downloads.

---

## 7. Verdict

**Is the legacy corpus still valid, or has it aged out?** On predicates, it has materially aged out: **51.5% of all
32,641 edges use a Biolink predicate that no longer exists in Biolink 4.2.2** (18 removed predicates, including the five
most-used in the database — `positively regulates`, `decreases activity of`, `increases activity of`, `negatively
regulates`, `increases abundance of`), plus 3 renamed — the predicted casualties of Biolink's qualifier refactor since
the v1.3.0 era DrugMechDB was built on. On nodes, the picture is better **but only partly visible**: of the **29.5% of
unique IDs (38.7% of occurrences) that are OBO-resolvable and were deep-checked**, ~97% are active and current, with
**40 obsolete, 4 unresolvable, and ~100 substantively drifted** labels — while the **dominant ~70% of unique IDs (61%
of occurrences; MeSH alone 49.5%), spanning UniProt, InterPro, DrugBank, Reactome, are non-OBO and were only sampled or
tabulated**, so MeSH label drift in
particular remains unmeasured. Net: the **node IDs are largely sound where checkable, but the predicate vocabulary has
drifted past half the corpus** — meaning a Biolink-version decision and a qualifier-aware predicate remap, not node
cleanup, is the gating effort for any backfill-or-re-curation choice.
