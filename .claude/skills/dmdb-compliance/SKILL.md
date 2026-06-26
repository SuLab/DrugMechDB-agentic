---
name: dmdb-compliance
description: Run and interpret the 4-layer QC gate on DrugMechDB path records, diagnose which layer failed and why, and judge whether a record is good enough to keep. Use when QC fails, when assessing corpus health, or when deciding if a curated path meets the bar.
---

# dmdb-compliance — QC gate & "good enough to keep"

Backs the whole QC stack (`scripts/qc.py`). Use it to run validation, read the
output, and reason about record quality.

## The gate

`scripts/qc.py` runs up to 4 layers, choosing the **profile** per file:

| Profile      | When                                   | Layers run |
|--------------|----------------------------------------|------------|
| `legacy`     | no `evidence:` block on any edge        | 1, 2, 3    |
| `ai_curated` | any edge carries an `evidence:` block   | 1, 2, 3, 4 |

| Layer | Script                       | Checks                                              |
|-------|------------------------------|-----------------------------------------------------|
| 1     | `validate_schema.py`         | LinkML schema (`MechanisticPath`): structure, required slots |
| 2     | `validate_node_ontology.py`  | node CURIE prefix ↔ Biolink label (see **dmdb-terms**) |
| 3     | `validate_predicates.py`     | every edge `key` ∈ the 67-predicate Biolink enum    |
| 4     | `validate_references.py`     | every snippet verbatim in its source (see **dmdb-references**) |

Exit codes: **0** all pass · **1** a layer failed · **2** no files found.

## Commands

```bash
just qc                       # whole corpus, auto profile
just qc kb/paths/<file>.yaml  # one record
just qc-layer 2 <file>        # isolate a failing layer
just qc-json <file>           # machine-readable {results[], overall_pass}
just qc-ai <file>             # force ai_curated (require evidence)
```

## Diagnosing failures

- **Layer 1** → a structural/schema problem (missing `graph._id`, malformed
  node/edge, < 2 nodes or < 1 link). Fix the YAML shape first; later layers
  assume it parses.
- **Layer 2** → prefix↔label mismatch → invoke **dmdb-terms**.
- **Layer 3** → an off-vocabulary predicate. Run `just canonicalize-write` to map
  known aliases to canonical predicates, then re-check; if still failing the
  predicate isn't in the enum and the edge needs rewording.
- **Layer 4** → snippet not found in cached source → invoke **dmdb-references**
  (fetch the PMID into `references_cache/` and copy the snippet verbatim).

## Good-enough-to-keep

A record is keepable when: QC is **green for its profile**; the path reads
**drug → protein target → … → disease** in **3–7 links**; branches only where
multiple actions *converge*; and the **net direction of influence is negative**
(walking drug→disease, the disease ends up *decreased*). These path-quality
conventions are correctness criteria, not style — see `CurationGuide.md`.
