# Node-Name Drift Audit — the non-OBO majority (MeSH-led)

**Scope:** READ-ONLY (measurement only; no fixes)
**Companion to:** [`biolink_ontology_drift_report.md`](biolink_ontology_drift_report.md) — this closes that report's stated coverage gap.
**Machine-readable:** [`drift_audit_mesh.json`](drift_audit_mesh.json)

> **Why this exists.** The first pass deep-checked only the OBO subset (~29.5% of unique IDs) and could only *spot-check or
> tabulate* the non-OBO majority — including **MeSH, which is 49.5% of all unique IDs and holds the drug and disease names
> the maintainers specifically suspected of drifting.** This pass resolves every non-OBO ID against its **own authority** (NLM MeSH,
> UniProt, EBI InterPro, Reactome ContentService, MyChem for DrugBank) and asks, per ID: does it still resolve? is it
> current (not retired/merged)? does the stored `name` still correspond to it? All API-free HTTP, cached, no OAK downloads.

Each ID is binned with the same honesty discipline as the OBO label-drift pass (benign synonyms are **not** errors):

| Bucket | Meaning |
|---|---|
| ✅ `match_preferred` | stored name = current **preferred** term |
| 🟡 `synonym` | stored name is a registered **entry term / synonym** of that ID (expected; DrugMechDB often used a common name — **not an error**) |
| ⚠️ `substantive_drift` | stored name is **neither** preferred nor any synonym (real mislabel, wrong ID, or a non-ontology name) |
| ❗ `deprecated` | ID exists but is **retired / merged / secondary** (replacement noted where available) |
| ❗ `unresolvable` | ID returns nothing |

---

## 1. Coverage achieved — the gap is now closed

| | Unique IDs | % of corpus (5,128) |
|---|---:|---:|
| Deep-checked in the **first** (OBO) pass | 1,514 | 29.5% |
| **Newly checked here** (non-OBO) | 3,609 | 70.4% |
| **Total now checked** | **5,123** | **99.9%** |
| Still uncheckable | 5 | 0.1% |

The only IDs still unverifiable are **5 DrugBank sub-IDs** (`DBMET…` / `DBSALT…` — metabolite/salt records with no open resolver). Silence no longer hides anywhere in the node layer.

---

## 2. MeSH — the primary deliverable (2,539 unique IDs · 11,633 occurrences · 100% checked)

| Bucket | Unique | % | Occurrences |
|---|---:|---:|---:|
| ✅ match_preferred | 2,085 | 82.1% | 10,549 |
| 🟡 synonym | 219 | 8.6% | 596 |
| ⚠️ substantive_drift | 142 | 5.6% | 284 |
| ❗ deprecated | 93 | 3.7% | 204 |
| ❗ unresolvable | 0 | 0% | 0 |

**By node type — the drug/disease answer:**

| Node label | match_pref | synonym | substantive_drift | deprecated |
|---|---:|---:|---:|---:|
| **Drug** | 1,226 | 137 | 47 | **93** |
| **Disease** | 570 | 76 | 86 | **0** |
| ChemicalSubstance | 172 | 2 | 6 | 0 |
| (other types) | 117 | 5 | 3 | 0 |

### 2a. ❗ Deprecated — 93, **all Drug nodes** (the real "drug IDs aged out" finding)

Every deprecated MeSH ID is a **Supplementary Concept Record (`C…`) that NLM has obsoleted** and mapped to a current
descriptor. The preferred term is literally `[OBSOLETE] <name>`; the replacement is in the record. Examples:

| ID | Stored name | NLM replacement |
|---|---|---|
| MESH:C047781 | lamotrigine | → D014227 |
| MESH:C078049 | Gatifloxacin | → D024841 |
| MESH:C059500 | meropenem | → D013845 |
| MESH:C043266 | Cefepime | → D002511 |
| MESH:C554127 | interferon alfa-2b | → D016898 |

These are genuine validity casualties — the ID is retired — but each has a clean 1:1 replacement, so they are mechanically remappable.

### 2b. ⚠️ Substantive drift — 142, **overwhelmingly name-label mismatch, not wrong IDs**

The IDs resolve and are current; the stored `name` simply isn't a registered MeSH term for that ID. Two benign patterns dominate:

- **Disease nodes (86):** DrugMechDB stored the **indication / common / un-inverted name** instead of the MeSH preferred term — e.g. `D011471` "Malignant tumor of prostate" vs **"Prostatic Neoplasms"**; `D000072861` "Social phobia" vs **"Phobia, Social"**; `D015464` "CML (ph+)" vs **"Leukemia, Myelogenous, Chronic, BCR-ABL Positive"**. The ID is correct.
- **Drug nodes (47):** mostly **INN/BAN vs USAN spelling** — `D002762` "Colecalciferol" vs **"Cholecalciferol"**; `C084555`/`D…` "valaciclovir" vs **"valacyclovir"**; `D005443` "Flumetasone" vs **"Flumethasone"**.

These are not invalid nodes; they are cases where the stored label should arguably be an `alt_name`. A small minority may be worth a curator's eye, but this bucket is **not** evidence that the MeSH IDs aged out.

> **Direct answer for MeSH:** disease IDs are **100% resolvable and current** (0 deprecated, 0 unresolvable); their name drift is benign labeling. The only hard MeSH validity problem is **93 retired drug SCRs (3.7%)**, all with mapped replacements.

---

## 3. The rest of the non-OBO layer

### UniProt (776 · 7,055 occ · 100% checked)
| ✅ | 🟡 | ⚠️ | ❗dep | ❗unres |
|---:|---:|---:|---:|---:|
| 605 | 56 | 90 | 22 | 3 |

- **22 deprecated** = `DELETED`/merged accessions (bacterial TrEMBL entries excluded from proteomes, e.g. `D0RGV5`, `A0A156J405`).
- **3 unresolvable** = **malformed accessions** — `UniProt:41972`, `UniProt:P3535`, `UniProt:P4984` (truncated/non-conformant; real curation errors).
- 90 substantive = stored protein/gene name differs from the current UniProt recommended name (mostly benign; some renamed proteins).

### InterPro (103 · 879 occ · 100%) · Pfam (16) · TIGR (1)
| prefix | ✅ | ⚠️ | ❗dep | ❗unres |
|---|---:|---:|---:|---:|
| InterPro | 72 | 23 | **4** | 4 |
| Pfam | 13 | 3 | 0 | 0 |
| TIGR | 0 | 1 | 0 | 0 |

- **4 InterPro deprecated** = entries **deleted** by EBI (HTTP 410 with deletion dates), e.g. `IPR015680` "Glutamate-Gated Chloride Channel" (deleted 2022-08-26), `IPR017320` (2023-10-13).
- **4 InterPro unresolvable** are **mis-prefixed IDs filed under `InterPro:`** — `SSF50353` (SUPERFAMILY), `cd15058` (CDD), `PR001696` (PRINTS-style) — i.e. wrong-namespace curation errors, not InterPro drift.

### DrugBank (98 · 220 occ · 94.9% — 5 sub-IDs uncheckable)
| ✅ | 🟡 | ⚠️ | uncheckable |
|---:|---:|---:|---:|
| 81 | 4 | 8 | 5 |

- All 93 standard `DB#####` accessions resolve via MyChem. The 5 uncheckable are `DBMET…`/`DBSALT…` metabolite/salt sub-IDs (no open resolver) — flag, don't infer validity.

### Reactome (81 · 329 occ · 100%)
| ✅ | ⚠️ | ❗unres |
|---:|---:|---:|
| 65 | 8 | 8 |

- 8 unresolvable: a mix of **retired/restructured stable IDs** (`R-HSA-140834`, `R-HSA-8932339`) and **zero-width-contaminated IDs** (see §4).

---

## 4. Cross-cutting data-hygiene findings (cheap fixes, real impact)

- **Zero-width character contamination — 6 IDs** carry a trailing `U+FEFF` (invisible BOM), making them unresolvable even though the underlying ID is fine: 1 InterPro (`IPR001128␏`) + 5 Reactome (`R-HSA-416476␏`, `-416482`, `-418555`, `-629587`, `-629594`). Stripping the character would resolve them.
- **Wrong-namespace IDs** filed under a prefix that doesn't match the ID scheme: `InterPro:SSF50353` (SUPERFAMILY), `InterPro:cd15058` (CDD), and the malformed `UniProt:41972` / `P3535` / `P4984`. These are curation typos, not ontology drift.

---

## 5. Whole node layer — combined (OBO first pass + non-OBO this pass)

Across **all 5,128 unique node IDs**, now **99.9% checked**:

| Outcome | Unique IDs | % of all |
|---|---:|---:|
| Resolves, current, name OK (preferred or synonym) | ~4,570 | **89.1%** |
| ⚠️ Substantive name drift (mostly benign labeling) | 375 | 7.3% |
| ❗ Deprecated / obsolete (retired ID, usually replaceable) | 159 | 3.1% |
| ❗ Unresolvable (wrong/retired/contaminated ID) | 19 | 0.4% |
| Uncheckable (DrugBank sub-IDs) | 5 | 0.1% |

**Hard ID-validity problems = deprecated + unresolvable = 178 IDs (3.5%).** The 375 name-drift IDs are dominated by
DrugMechDB storing common/indication/spelling-variant names rather than the authority's preferred term — a labeling
convention, not an invalid node.

---

## 6. Reproducibility

Deterministic; every response cached under `audit_work/resolve_cache/<prefix>/` (reruns are free). No OAK downloads.

```bash
export SSL_CERT_FILE="$(.venv-py310/bin/python -c 'import certifi; print(certifi.where())')"   # macOS framework-Python TLS
python audit_work/nonobo_resolve.py MESH        # NLM MeSH lookup/details (D and C); .json fallback for active/retired
python audit_work/nonobo_resolve.py UniProt     # UniProt REST (entryType Inactive => deprecated)
python audit_work/nonobo_resolve.py InterPro    # EBI InterPro API (410 => deleted)
python audit_work/nonobo_resolve.py Pfam ; python audit_work/nonobo_resolve.py TIGR
python audit_work/nonobo_resolve.py DB          # MyChem drugbank.id (sub-IDs uncheckable)
python audit_work/nonobo_resolve.py reactome    # Reactome ContentService
python audit_work/aggregate_nonobo.py           # -> docs/drift_audit_mesh.json (+ whole-layer rollup, zero-width scan)
```

---

## 7. Verdict — are the node names still valid?

With the non-OBO majority now measured (coverage **29.5% → 99.9%**), the node layer is **largely sound, and far healthier
than the predicate layer.** Of all 5,128 unique IDs, **~89% resolve, are current, and carry the preferred term or a
registered synonym; only 3.5% (178 IDs) have a hard validity problem** — and those are concentrated and individually
fixable: **93 retired MeSH drug SCRs** (all with 1:1 NLM replacements), 22 deleted UniProt accessions, a handful of
deleted InterPro families and retired/contaminated Reactome IDs, plus ~19 outright-bad IDs (malformed accessions,
wrong-namespace prefixes, 6 zero-width-character contaminations). A further **7.3% show name drift, but that is
overwhelmingly benign** — DrugMechDB storing a common name, the disease *indication* name, an un-inverted form, or an
INN/BAN spelling variant rather than the authority's preferred term (the IDs themselves resolve and are current);
notably, **MeSH disease IDs are 100% resolvable and current.** So the direct answer to the maintainers' suspicion: the **node
IDs did not substantially age out** (≈96.5% valid), and the apparent "name drift" is mostly a labeling-convention gap,
not invalid identifiers — the opposite of the predicate finding, where **51.5% of edges use a predicate Biolink has
removed.** The corpus's aging problem lives in its *relationships*, not its *entities*.
