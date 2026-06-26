# Predicate Qualifier-Remap — sizing the bring-to-current-Biolink transform

**Scope:** READ-ONLY proposal / sizing — **no remap applied, no record/schema/enum edits.**
**Companion to:** [`biolink_ontology_drift_report.md`](biolink_ontology_drift_report.md) · **Machine-readable:** [`predicate_qualifier_remap.json`](predicate_qualifier_remap.json)

> Sizes the fix for the predicate half of the drift audit: the **18 predicates removed** from Biolink 4.2.2 (16,812 edges = 51.5% of the corpus) + the **3 renamed**. Each target was verified against Biolink 4.2.2 — core predicates and qualifier slots via `bmt`, qualified forms via the model's own [`predicate_mapping.yaml`](https://github.com/biolink/biolink-model/blob/v4.2.2/predicate_mapping.yaml) (v4.2.2). **No qualifier name or value is invented.**

## Mapping table

| Old predicate | Corpus edges | → Target (Biolink 4.2.2) | Class | Source / note |
|---|---:|---|---|---|
| `positively regulates` | 6,630 | `regulates` · object_direction_qualifier=`upregulated` | qualifier-expansion | predicate_mapping.yaml: mapped under 'entity/process positively regulates …'; no qualified_predicate |
| `decreases activity of` | 4,561 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`activity` · object_direction_qualifier=`decreased` | qualifier-expansion | predicate_mapping.yaml |
| `increases activity of` | 1,974 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`activity` · object_direction_qualifier=`increased` | qualifier-expansion | predicate_mapping.yaml |
| `negatively regulates` | 1,913 | `regulates` · object_direction_qualifier=`downregulated` | qualifier-expansion | predicate_mapping.yaml: mapped under 'entity/process negatively regulates …'; no qualified_predicate |
| `increases abundance of` | 1,028 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`abundance` · object_direction_qualifier=`increased` | qualifier-expansion | predicate_mapping.yaml |
| `decreases abundance of` | 476 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`abundance` · object_direction_qualifier=`decreased` | qualifier-expansion | predicate_mapping.yaml |
| `molecularly interacts with` | 109 | `directly physically interacts with` | rename | bmt-verified-rename: documented Biolink deprecation replacement; semantic narrowing — broader alt 'interacts with' also exists (curator may prefer it) |
| `affects risk for` | 82 | needs human call → one of: `associated with increased likelihood of`, `associated with decreased likelihood of`, `contributes to` | needs-review | bmt-verified-rename: sign-dependent: maps to increased- vs decreased-likelihood per edge; resolvable by reading the edge's intended direction, but not a single 1:1 rule |
| `prevents` | 44 | `preventative for condition` | rename | bmt-verified-rename: already flagged renamed in drift audit |
| `ameliorates` | 12 | `ameliorates condition` | rename | bmt-verified-rename: already flagged renamed in drift audit |
| `increases degradation of` | 9 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`degradation` · object_direction_qualifier=`increased` | qualifier-expansion | predicate_mapping.yaml |
| `contraindicated for` | 8 | `contraindicated in` | rename | bmt-verified-rename |
| `increases transport of` | 7 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`transport` · object_direction_qualifier=`increased` | qualifier-expansion | predicate_mapping.yaml |
| `directly interacts with` | 5 | `directly physically interacts with` | rename | bmt-verified-rename |
| `increases stability of` | 4 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`stability` · object_direction_qualifier=`increased` | qualifier-expansion | by-analogy: aspect 'stability' exists in GeneOrGeneProductOrChemicalEntityAspectEnum; explicit row not shipped in predicate_mapping.yaml but the +increases/-decreases pattern is fully systematic |
| `exacerbates` | 3 | `exacerbates condition` | rename | bmt-verified-rename: already flagged renamed in drift audit |
| `decreases synthesis of` | 2 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`synthesis` · object_direction_qualifier=`decreased` | qualifier-expansion | predicate_mapping.yaml |
| `increases expression of` | 1 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`expression` · object_direction_qualifier=`increased` | qualifier-expansion | predicate_mapping.yaml |
| `decreases expression of` | 1 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`expression` · object_direction_qualifier=`decreased` | qualifier-expansion | predicate_mapping.yaml |
| `decreases uptake of` | 1 | `affects` · qualified_predicate=`causes` · object_aspect_qualifier=`uptake` · object_direction_qualifier=`decreased` | qualifier-expansion | predicate_mapping.yaml |
| `predisposes` | 1 | `predisposes to condition` | rename | bmt-verified-rename |

## Sizing summary

- **Total drifted edges (18 removed predicates):** 16,812  (+59 from the 3 renamed = 16,871 total touched)
- **Covered by clean deterministic rules:** 16,789 edges = **99.51%** of all touched edges
  - 13 **qualifier-expansion** rules (change edge shape: add `predicate`+qualifier slots)
  - 7 **rename** rules (1:1 label swap)
- **Needs human review:** 82 edges = **0.49%** (1 predicate)
- **Distinct rules total:** 21  (13 qualifier-expansion + 7 rename + 1 needs-review)

### Needs-review (the only non-deterministic case)

- `affects risk for` (82 edges) — sign-dependent: maps to increased- vs decreased-likelihood per edge; resolvable by reading the edge's intended direction, but not a single 1:1 rule

## Where this artifact is applied (a maintainer decision — not decided here)

This mapping is **identical** whether the corpus is migrated or translated; only the application point differs:

- **Option B (rewrite records):** this table is the **migration script** — apply once, records gain qualifier fields. Requires the schema/enum to admit `qualified_predicate` + `object_aspect_qualifier` + `object_direction_qualifier` slots (an additive schema change), and revisits the 'no reformatting' boundary.
- **Option C (translate at export):** this table is the **publish-time transform** — storage stays exactly as today (legacy `key` predicates preserved), and the current-Biolink/qualified form is emitted only in the published KGX/TRAPI output. Zero change to `kb/paths/`.

The artifact does not pick an option.

## Verdict

Bringing the corpus to current Biolink is **overwhelmingly a mechanical transform, not a curation effort**: **99.51% of touched edges** (16,789) are covered by **20 deterministic rules** — 13 qualifier-expansions (verified against Biolink's own predicate_mapping.yaml) and 7 plain renames — leaving a **single needs-review predicate** (`affects risk for`, 82 edges = 0.49%), whose target is merely sign-dependent and resolvable per-edge. The cost is not curation labor but a **schema decision**: qualifier-expansion changes the edge shape, so the real question the maintainers face is *where* to apply this one table — migrate records (option B, additive schema change) or translate at export (option C, storage untouched) — not *how much human curation* it takes (almost none).
