# Multi-Path-per-File Convention

**PRD reference:** [PRD v3 §4.1, §7 Open Q #2](PRD_v3.md)
**Date:** May 2026
**Status:** Confirmed — kept as default for v3

## Decision

When a single (drug, disease) pair is curated with more than one distinct mechanism, **each mechanism is stored as a separate file**. The filename suffix `_1`, `_2`, … indexes the mechanism within the pair:

```
kb/paths/DB01244_MESH_D000787_1.yaml
kb/paths/DB01244_MESH_D000787_2.yaml
…
kb/paths/DB01244_MESH_D000787_8.yaml
```

The alternative — one file containing multiple path objects — is **rejected** for v3.

## Why this is the right call for v3

1. **Per-file validation and PR review are cleaner.** Layer 1–4 validation runs cleanly file-by-file; GitHub diffs and PR review map 1:1 to a single mechanism. A multi-path-per-file design would force reviewers to context-switch between mechanisms in the same diff.
2. **The agent loop is simpler.** `/curate [Drug] for [Disease]` produces one path. If the agent later finds a second mechanism, it produces a second file — no merging required.
3. **No conflict with the LinkML schema.** `MechanisticPath` is declared with `tree_root: true`; the schema models a single mechanism per document. Adding multi-mechanism support would require either a wrapper class or a list-of-paths root, both of which complicate downstream tooling.
4. **Backfill maps naturally.** `kb/paths/_backfill_status.yaml` tracks one status per file; this stays consistent under the per-file convention.

## Current corpus shape

Confirmed by surveying `kb/paths/` on the cleaned post-Phase-1 data:

| Mechanisms per pair | Distinct drug–disease pairs |
|---|---|
| 1 | 4,493 |
| 2 | 133 |
| 3 | 12 |
| 4 | 3 |
| 5 | 5 |
| 6 | 1 |
| 8 | 1 |
| **Total** | **4,648** |

Total path files: **4,846** across **4,648** unique pairs, so the convention is already universally in use; no migration needed.

The five pairs with the most mechanisms:

| File-stem prefix | Mechanisms |
|---|---|
| `DB01244_MESH_D000787` | 8 |
| `DB05812_MESH_D011471` | 6 |
| `DB00313_MESH_D001714` | 5 |
| `DB00508_MESH_D011618` | 5 |
| `DB09078_MESH_D000077273` | 5 |

## How the agent and validators should treat siblings

- **Sibling discovery:** `kb/paths/_index.yaml` contains one entry per file, including pairs with multiple mechanisms. Agents listing mechanisms for a pair should group by `(drugbank, disease_mesh)` rather than relying on filename parsing.
- **Cross-mechanism consistency is not enforced by Layer 1.** Two mechanisms may legitimately disagree on the intermediate biology while both being correct (e.g. distinct receptor subtypes). Layer 2 (node ontology) and Layer 4 (evidence) handle internal consistency per file; cross-file checks are out of scope for Phase 1.
- **Re-indexing is not automatic.** If a mechanism is retracted, its file is deleted but the remaining files retain their suffixes (e.g. deleting `_2` does not renumber `_3` → `_2`). This preserves stable `_id` references in any external citations.

## Out-of-scope follow-ups (recorded, not actioned in Phase 1)

- A multi-mechanism viewer in the QC dashboard (Phase 4) should group sibling files visually.
- A future "merge mechanisms" workflow may be needed if curators wish to combine two near-identical paths; defer to Phase 4 when actual demand is measurable.
