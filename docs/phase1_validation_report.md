# Phase 1 Validation Report

**PRD reference:** [PRD v3 §6 Phase 1](PRD_v3.md)
**Date:** May 2026
**Schema:** [`src/drugmechdb/schema/drugmechdb.yaml`](../src/drugmechdb/schema/drugmechdb.yaml), validating against class `MechanisticPath`
**Files validated:** 4,846 (every file under `kb/paths/` except `_index.yaml`)

## Final result

| | Files | % |
|---|---|---|
| Pass | **4,846** | **100.0%** |
| Fail | 0 | 0.0% |

Exit criterion from PRD v3 Phase 1 is met.

## Tooling

Validation runs via [`scripts/phase1_validate_all.py`](../scripts/phase1_validate_all.py), which:
1. Compiles the LinkML schema to JSON Schema with `linkml.generators.jsonschemagen.JsonSchemaGenerator` (top class: `MechanisticPath`).
2. Validates each `kb/paths/*.yaml` with `jsonschema.Draft7Validator.iter_errors`.
3. Aggregates failures by normalized message pattern.
4. Writes machine-readable per-file failures to `docs/phase1_validation_failures.json` and this human-readable report.

A per-file `linkml-validate` invocation against the same schema produces equivalent results but is ~100× slower; the batch validator above is used for routine Phase 1 work and the CLI is used for spot-checks.

To reproduce:
```
python -m venv .venv && .venv/bin/pip install linkml linkml-runtime jsonschema pyyaml
.venv/bin/python scripts/phase1_validate_all.py
```

## Failure landscape — initial run (before fixes)

Initial run reported **4,846 / 4,846 (100%) failing**. The aggregated buckets were:

| # | Files | Occurrences | Normalized error |
|---|---|---|---|
| 1 | 4,845 | 4,845 | `graph` value is an object but schema generated `type: string` |
| 2 |    99 |   102 | Node-level `alt_name` field — schema declares `alt_names` (plural) |
| 3 |    10 |    14 | Node-level `alt_ids` scalar (e.g. `alt_ids: MESH:D014276`) — schema expects array |
| 4 |     8 |     8 | A second `alt_ids` scalar pattern (MESH:C-prefixed) |
| 5 |     5 |     5 | Node-level `alt-name` (hyphen) — same problem as #2 |
| 6 |     2 |     2 | Node-level `reference: <url>` — schema has no such PathNode slot |
| 7 |     1 |     1 | Top-level `references` is a single whitespace-joined URL string |
| 8 |     1 |     1 | Node-level `all_id` — schema declares `alt_ids` |
| 9 |     1 |     1 | Tazanolast file: `graph` type-string failure with `drugbank: null` |

A separate scan also surfaced **silently-dropped legacy fields** that did not fail validation (because the root JSON Schema is open at the top level), but represent quiet data loss when read schema-aware:

| Field at top level | Files | Canonical |
|---|---|---|
| `reference` (singular) | 4,743 | `references` |
| `comments` (plural) | 52 | `comment` |
| `commments` (misspelling) | 1 | `comment` |
| `comemnt` (misspelling) | 1 | `comment` |
| `drugbank: null` | 2 | absent |
| `drug_mesh: null` | 50 | absent |

Phase 1 normalized these as well so that future schema-aware reads do not silently drop curator-entered data.

## Fixes applied

### Schema fixes — [`src/drugmechdb/schema/drugmechdb.yaml`](../src/drugmechdb/schema/drugmechdb.yaml)

1. **`graph` slot: added `inlined: true`.** Without this, LinkML's JSON Schema generator treats a class-ranged slot as an identifier reference, emitting `type: string` instead of `$ref: PathMetadata`. This single change resolved bucket #1.
2. **`PathMetadata.drugbank`: required → optional.** A small subset of paths use a MESH-only drug identifier (e.g. `MESH:C106301` for tazanolast). The schema now allows either `drugbank` or `drug_mesh` to be absent; Phase 2 will add a lint that enforces at least one drug identifier is present.
3. **`PathMetadata.drug_mesh`: required → optional.** Parallel rationale: 50 paths have a `DrugBank` ID but no MESH binding (e.g. collagenase, laronidase).

### Data normalizations — [`scripts/phase1_normalize_paths.py`](../scripts/phase1_normalize_paths.py)

Idempotent one-shot rewriter. Final run touched **4,747 of 4,846 files** with these change counts:

| Change | Count |
|---|---|
| Top-level `reference` → `references` (rename; ensure list) | 4,743 |
| Node-level `alt_name` → `alt_names` | 102 |
| Top-level `comments` → `comment` | 52 |
| Node-level `alt_ids` scalar → list | 22 |
| Path-level `drug_mesh: null` → absent | 50 |
| Node-level `alt-name` → `alt_names` | 5 |
| Node-level `reference: <url>` promoted to top-level `references` | 2 |
| Top-level `commments` (misspelling) → `comment` | 1 |
| Top-level `comemnt` (misspelling) → `comment` | 1 |
| Top-level `references` scalar (whitespace-joined URLs) → list | 1 |
| Node-level `all_id` → `alt_ids` | 1 |
| Path-level `drugbank: null` → absent | 1 |
| Path-level literal `drug_mesh: MESH:null` placeholder → absent | 9 |

Idempotency was confirmed by a second run, which reported 0 files touched.

## Final pass

| | Files | % |
|---|---|---|
| Pass | **4,846** | **100.0%** |
| Fail | 0 | 0.0% |

## Caveats and limitations

- **Root JSON Schema is open.** LinkML generates the root document with `additionalProperties: true` even though the named `MechanisticPath` definition has `additionalProperties: false`. As a result, the current validator does not flag unknown keys at the document root. Tightening this is a Phase-2 task; it requires either patching the generator output or wrapping documents in an explicit `{"$ref": "#/$defs/MechanisticPath"}` envelope before validation.
- **This is Layer-1 only.** Layer 2 (node ontology checks), Layer 3 (predicate validation against `BiolinkPredicate`), and Layer 4 (PubMed snippet verification) all land in Phase 2. Layer 3 is gated on Phase 1.5 (predicate canonicalization), since many edges still use predicates that exist in `biolink_predicates.yaml` but in slightly different surface forms.
- **No deletions performed.** `utils/deprecated_ids.txt` lists path IDs marked deprecated by prior curation work. Phase 1 did not delete the corresponding files; that decision moves to Phase 2 alongside the broader cleanup described in [`tooling_audit.md`](tooling_audit.md).
- **The monolith is unchanged.** `indication_paths.yaml` (272K lines) was not touched. The per-file copies under `kb/paths/` are now the canonical source of truth; the monolith remains as a frozen backup for the duration of Phase 2 backfill, then will be archived.
- **`kb/paths/_index.yaml` regenerated.** The index was originally produced by `scripts/split_monolith.py` from the monolith and carried stale `drugbank: null` / `drug_mesh: null` entries. [`scripts/rebuild_index.py`](../scripts/rebuild_index.py) regenerates the index from the per-file YAML; run it after any further bulk normalization.
