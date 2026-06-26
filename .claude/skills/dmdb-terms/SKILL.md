---
name: dmdb-terms
description: Add and validate ontology term references (CURIE ids + canonical labels) on DrugMechDB path nodes. Use when a node's id/label/name may be wrong, when QC Layer 2 (node ontology) fails, or when resolving a drug/protein/process name to the right ontology id.
---

# dmdb-terms — node ontology terms

Every node in a path record is `{id (CURIE), label (Biolink type), name}`. This skill
keeps those three internally consistent and resolvable. It backs **QC Layer 2**
(`scripts/validate_node_ontology.py`).

## The rule

A node's CURIE **prefix must match the canonical ontology for its Biolink `label`**, and
its `name` should be the ontology's canonical label for that id.

| Biolink `label`           | Canonical prefix(es)   |
|---------------------------|------------------------|
| Drug                      | `MESH`, `DB`           |
| Protein                   | `UniProt`              |
| BiologicalProcess         | `GO`                   |
| MolecularActivity         | `GO`                   |
| CellularComponent         | `GO`                   |
| Cell                      | `CL`                   |
| Pathway                   | `REACT` / `Reactome`   |
| Disease                   | `MESH`                 |
| PhenotypicFeature         | `HP`                   |
| GrossAnatomicalStructure  | `UBERON`               |
| ChemicalSubstance         | `MESH`, `CHEBI`        |
| GeneFamily                | `InterPro`             |
| OrganismTaxon             | `NCBITaxon`            |
| MacromolecularComplex     | `PR`                   |

Legacy prefixes (`taxonomy`, `reactome`, `Pfam`, `TIGR`) produce **warnings**, not
failures — don't "fix" them unless you're deliberately migrating a record.

## Workflow

1. **Resolve / verify an id.** Prefer **OAK** (authoritative, offline, deterministic):
   - `.venv-py310/bin/runoak -i sqlite:obo:go info GO:0006915`
   - For interactive search use the `ols-mcp` MCP (`mcp__ols-mcp__search`).
   - For a non-OBO drug/protein *name* → id (MeSH, DrugBank, UniProt), OAK is weak;
     use BioThings / the name as documented in `AGENTS.md`. **Node Normalizer is not used.**
2. **Set `name` to the canonical label** OAK returns — not a synonym you prefer.
3. **Check prefix↔label** against the table above.
4. **Validate:** `just qc-layer 2 kb/paths/<file>.yaml` (or `just qc <file>` for all layers).

## Notes / gotchas

- The pre-edit hook runs QC on every write, so a bad id is caught before it lands.
- CURIE casing matters (`UniProt`, not `uniprot`). Match the prefixes above exactly.
- Layer 2 today is **prefix-only** (it does not yet confirm the id *exists* in the
  ontology or that `name` matches the canonical label). Running OAK by hand closes
  that gap until the `--deep` ontology check is wired in (see `docs/biolink_ontology_drift_report.md`).
