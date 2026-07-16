# DrugMechDB — agentic, self-validating rebuild

**DrugMechDB** captures the mechanistic path from a drug to a disease for a given
indication: a directed, [Biolink Model](https://biolink.github.io/biolink-model/)-typed
graph that walks `Drug → molecular target → … → Disease` through biomedical entities.

This repository is the **agentic, self-validating rebuild** of DrugMechDB: the same
gold-standard content (**4,846 mechanistic paths**), re-organized as one file per record
and wrapped in a machine-checked quality gate and a curation harness. Every change is
**additive and format-compatible** — the record format is preserved; the machinery is
built *around* it.

- One directed cause→effect multigraph per record, joined by CURIE identifiers.
- A deterministic **4-layer QC gate** that is the single source of truth for validity.
- An agentic curation harness with a **pre-edit hook** that blocks invalid writes.
- An independent **semantic critic** that re-derives each edge's evidence.
- Deterministic **publish** tooling that regenerates the consolidated artifacts.

## Resources (the published DrugMechDB)

- **Publication:** Gonzalez-Cavazos, A. C., Tanska, A., Mayers, M., Carvalho-Silva, D.,
  Sridharan, B., Rewers, P. A., Sankarlal, U., Jagannathan, L., & Su, A. I. (2023).
  *DrugMechDB: a curated database of drug mechanisms.* Scientific Data, 10(1), 632.
  [Read it](https://www.nature.com/articles/s41597-023-02534-z)
- **Release / DOI:** [10.5281/zenodo.8139357](https://doi.org/10.5281/zenodo.8139357)

## Repository layout

| Path | What |
|---|---|
| `kb/paths/*.yaml` | **Source of truth** — one record per file (4,846 records) |
| `kb/paths/_index.yaml` | Generated index (do not hand-edit) |
| `indication_paths.{yaml,json}` | Generated consolidated monoliths (do not hand-edit) |
| `src/drugmechdb/schema/` | LinkML schema (`MechanisticPath`) + Biolink node/predicate vocabularies |
| `scripts/` | QC gate, curation/evidence tools, publish + data-hygiene tooling |
| `scripts/quality/` | Deterministic structural scorer + semantic critic |
| `.claude/` | Agentic harness — commands, skills, and the pre-edit validation hook |
| `AGENTS.md`, `CurationGuide.md` | The curation contract and the detailed guide |
| `docs/PIPELINE.md` | End-to-end setup → curate → validate → publish |

## The record format

Each `kb/paths/{drugbank}_{disease_mesh}_{n}.yaml` is a NetworkX-style node-link graph:

- `graph` — indication metadata (`_id`, drug/disease names + MeSH/DrugBank ids)
- `nodes` — each has a CURIE `id`, a Biolink `label`, and a `name`
- `links` — edges (`key` = Biolink predicate, `source`, `target`), joined by CURIE
- `references` — record-level sources (optional); edges may carry per-edge `evidence`
  (an `EvidenceItem` with a verbatim PubMed `snippet`)
- `directed: true`, `multigraph: true`

Node CURIE prefixes are canonical per Biolink type:

| Concept type | Identifier source |
|---|---|
| Drug | MESH, DrugBank |
| Protein | UniProt |
| BiologicalProcess / MolecularActivity / CellularComponent | GO |
| ChemicalSubstance | MESH, CHEBI |
| Disease | MESH |
| PhenotypicFeature | HP |
| Cell | CL |
| GrossAnatomicalStructure | UBERON |
| GeneFamily | InterPro |
| MacromolecularComplex | PR |
| OrganismTaxon | NCBITaxon |
| Pathway | Reactome |

## The QC gate

`scripts/qc.py` is the single source of truth for "is this record valid." It picks a
profile per file and runs the matching layers:

| Profile | When | Layers |
|---|---|---|
| `legacy` | no per-edge evidence | 1, 2, 3 |
| `ai_curated` | any edge has `evidence:` | 1, 2, 3, 4 |

1. **schema** (LinkML `MechanisticPath`) · 2. **node ontology** (CURIE prefix ↔ label,
plus an invisible/whitespace-character guard) · 3. **predicate enum** (67 Biolink
predicates) · 4. **reference** (every snippet is verbatim in its cited source).

```bash
just qc                       # whole corpus
just qc kb/paths/<file>.yaml  # one record
```

Exit `0` pass · `1` fail · `2` no files. The pre-edit hook
(`.claude/hooks/validate_path_hook.py`) runs the gate before any write to `kb/paths/`
lands and blocks invalid writes.

## Curation harness

- `/curate <Drug> for <Disease>` — curate a new path from cited PubMed evidence.
- `/backfill <record>` — add per-edge evidence to an existing path.
- After the QC gate passes, the **semantic critic** (`scripts/quality/critic.py`)
  independently re-derives each edge's support and judges the chain.

Curate only **established, already-asserted** mechanisms from sources that assert them;
every edge's evidence snippet must be a verbatim substring of a fetched reference. See
**`AGENTS.md`** (the contract) and **`CurationGuide.md`** (the guide).

## Getting started

```bash
python3.10 -m venv .venv-py310
.venv-py310/bin/pip install -r requirements.lock   # reproducible, pinned
.venv-py310/bin/pip install -e . --no-deps
just qc                                             # validate the corpus
```

Full setup and the end-to-end pipeline are in **`docs/PIPELINE.md`**.

## Contributing

Curate on a feature branch, run `just qc` until it passes, then open a PR — CI enforces
the same gate. Use targeted `git add` (the record and its cached references); never edit
the generated `_index.yaml` or the consolidated monoliths by hand (regenerate them with
`scripts/rebuild_monolith.py` / `just rebuild-index`).

## License

Code: MIT (see `LICENSE`). Curated data: CC0.

## Citation

```
Gonzalez-Cavazos, A. C., Tanska, A., Mayers, M., Carvalho-Silva, D., Sridharan, B.,
Rewers, P. A., Sankarlal, U., Jagannathan, L. & Su, A. I. (2023). DrugMechDB: A Curated
Database of Drug Mechanisms. Scientific Data, 10(1), 632.
```
