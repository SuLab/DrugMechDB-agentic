# Tooling Audit — DrugMechDB AI Curation Phase 1

**Audit date:** May 2026
**PRD reference:** [PRD v3 §3.3](PRD_v3.md)

This document inventories the existing scripts in the repository and decides — for each one — whether it is **kept**, **retired**, or **archived** under the v3 AI curation platform.

A working definition for this audit:
- **Keep** — used by the v3 validation / agent pipeline; remains in the runtime path.
- **Archive** — superseded but worth preserving as prior art; move to `attic/` (or equivalent) rather than delete, since it documents past design decisions.
- **Retire** — historical, no longer called by anything we care about, can be deleted on a future cleanup pass once nothing imports it.

---

## 1. `parse.py` (repo root)

**Purpose:** Generates the Jekyll-based documentation site (path pages, sidebars, overview tables) from `indication_paths.yaml`. Writes Markdown to `pages/mydoc/`, PNGs to `images/`, and YAML sidebars under `_data/sidebars/`.

**Inputs:** `indication_paths.yaml` (monolith), `CurationGuide.md`, `README.md`, `utils.build_indications.read_deprecated_ids()`.

**Outputs:** Markdown pages, plot images, sidebar YAML.

**Does it already convert YAML↔JSON?** No. It produces Markdown for Jekyll, not JSON.

**Does it handle the per-file `kb/paths/` layout?** No — hard-codes `indication_paths.yaml` in `read_yaml()`.

**Decision: Archive.** It is coupled to the legacy site-generation flow and the monolithic YAML. v3's dashboard story (PRD §5.5) replaces it. Move to `attic/legacy_site_gen/parse.py` so the Jekyll machinery (`_layouts/`, `_includes/`, `pages/`, `_data/`) can be retired in one coherent step.

---

## 2. `testfile.py` (repo root)

**Purpose:** None. The entire contents are:

```python
def test():
    pass
```

**Decision: Retire.** Stub with no callers and no test value. Delete on next cleanup pass.

---

## 3. `utils/` (testing and conversion utilities)

The real test scaffold lives here, not in `testfile.py`. Each file evaluated individually.

### 3.1 `utils/test_indications.py`
Parametrizes pytest cases over the entire monolith and runs `PathTester.run_tests()` on each.

- Reads `indication_paths.yaml` via `nx.read_yaml` — **broken on modern NetworkX** (removed after 2.5; project pins `networkx==2.5` to keep it alive).
- Iterates the monolith, not `kb/paths/`.

**Migration value:** the *shape* of the test (parametrize over paths, run a checker) is what we want — but driven by `kb/paths/*.yaml` and the LinkML schema instead of `PathTester`.

**Decision: Archive.** Replace in Phase 2 with `tests/test_validation.py` that runs `linkml-validate` and the three other layers per file.

### 3.2 `utils/pathtester.py`
A handwritten checker covering:
- Allowed CURIE prefixes (`ALLOWED_CURIS = {CHEBI, CL, DB, GO, HP, InterPro, PR, Pfam, MESH, NCBITaxon, REACT, TIGR, UBERON, UniProt, UNII}`)
- Required Biolink node labels via `utils/dmdb_to_bl_map.csv`
- Allowed Biolink predicates via `utils/biolink_preds.txt`
- Dict-key presence checks (`validate_dict_keys`)

This is **prior art for Layers 1–3** of the v3 validation pipeline. It pre-dates LinkML and does by hand what the schema now declares.

**Migration value:** the `ALLOWED_CURIS` set, `dmdb_to_bl_map.csv`, and `biolink_preds.txt` are useful cross-checks while bringing up the new validators — confirm the LinkML schema covers everything they covered before deleting.

**Decision: Archive (after Phase 2 cross-check).** Move to `attic/pathtester/` once Phase 2 has independently verified that the LinkML schema + `biolink_predicates.yaml` cover the same ground.

### 3.3 `utils/json_yaml_convert.py`
Generic `read_yaml`/`write_yaml`/`read_json`/`write_json` helpers using `yaml.safe_load` and `simplejson`. Format-agnostic; not coupled to the monolith.

**Decision: Keep.** Still useful for any JSON ↔ YAML round-tripping the agent may need (e.g., when shipping a path to a downstream consumer that prefers JSON). Move to `src/drugmechdb/io.py` in Phase 2 to bring it under the package layout.

### 3.4 `utils/build_indications.py`
Helper for `parse.py`. Reads `utils/deprecated_ids.txt` and provides `get_id_num()` (extracts the trailing `_N` from path IDs).

**Decision: Archive** alongside `parse.py` — same dependency chain.

### 3.5 `utils/convert_to_biolink.py`
Downloads an Excel file from Zenodo (DOI 8139357) and converts it. Historical ingestion path from the manuscript-era data drop.

**Decision: Retire.** The source of truth is now `kb/paths/`; we don't re-ingest from Zenodo.

### 3.6 `utils/xls_to_json.py`
Excel → JSON conversion. Same historical origin as 3.5.

**Decision: Retire.**

### 3.7 `utils/plot_paths.py`
Image generation for individual paths (for the legacy Jekyll site).

**Decision: Archive** alongside `parse.py`.

### 3.8 Data files: `utils/biolink_preds.txt`, `utils/dmdb_to_bl_map.csv`, `utils/deprecated_ids.txt`
These are reference data, not code.

- `biolink_preds.txt` — superseded by `src/drugmechdb/schema/biolink_predicates.yaml`. Used for cross-checking in Phase 1.5 canonicalization, then archive.
- `dmdb_to_bl_map.csv` — superseded by `src/drugmechdb/schema/biolink_nodes.yaml`. Same lifecycle.
- `deprecated_ids.txt` — list of path IDs marked deprecated. Decide in Phase 1 whether to (a) actually delete the corresponding `kb/paths/*.yaml` files, or (b) keep them with a `deprecated: true` flag on the metadata. Recommendation: option (a), and record the list in a `CHANGES.md`.

---

## 4. `data_tools/` (top-level directory)

A vendored copy of Mike Mayers's external `data_tools` package (see `data_tools/README.md`). Provides pandas/network utilities for hetnet construction, ML result plotting, and Wikipedia/Wikidata lookups.

- Not imported by any v3 component (`linkml-*` validators, agent skills, dashboard).
- Heavy dependency tail (`hetnetpy`, `wikidataintegrator==0.7.4`, `seaborn`, etc.) that doesn't belong in the AI curation runtime.
- One demo notebook (`data_tools/demo/Graph_Drawing_Demo.ipynb`) — non-blocking.

**Decision: Retire from the runtime path.** It is not in `pyproject.toml`'s `dependencies` and should not be. If anyone still uses the notebook, they can `pip install git+https://github.com/mmayers12/data_tools` on demand; the vendored copy can be deleted once that callsite is identified or confirmed gone.

---

## 5. `data_analysis/` (top-level directory)

Contains `figures_DMDB_manuscript.ipynb` plus frequency CSVs used in the original DrugMechDB manuscript.

**Decision: Archive.** Move to `attic/manuscript_2023/` so the figures remain reproducible. Not on the v3 runtime path.

---

## 6. `scripts/`

### 6.1 `scripts/split_monolith.py`
Already executed; produced the 4,846 files now in `kb/paths/` plus `_index.yaml`. Idempotent and re-runnable if the monolith ever changes.

**Decision: Keep.** Useful for backfill verification (round-trip: split monolith → diff against `kb/paths/` → confirm no drift). Add a `--check` mode in Phase 2 that diffs instead of writing.

### 6.2 `scripts/update_occurs_in_preserving_format.py`
One-shot fix that rewrote `occurs in` → `phenotype of` for `(PhenotypicFeature → Disease)` edges. Already applied.

**Decision: Archive.** Move to `attic/migrations/` as evidence of a past schema change. Phase 1.5 (predicate canonicalization) will use a more general framework.

---

## 7. `requirements.txt`

Currently:
```
pytest==7.4.0
pandas==2.0.3
matplotlib==3.5.1
pyyaml
xlsxwriter==3.1.2
xlrd==1.2.0
simplejson==3.19.1
networkx==2.5
biothings_client==0.3.0
git+https://github.com/mmayers12/path_plots
scipy==1.10.1
```

Most of these support the legacy parser (`parse.py`), the Excel ingestion path, or `path_plots`. `networkx==2.5` is pinned only to keep `nx.read_yaml` alive in `utils/test_indications.py`.

The real v3 runtime dependencies already live in `pyproject.toml`:
- `linkml-runtime>=1.9.4`
- `linkml-reference-validator>=0.1.8`
- `linkml-term-validator>=0.4.0`
- `pyyaml>=6.0`
- `httpx>=0.25.0`
- `typer>=0.9.0`

Dev: `linkml>=1.9.3`, `pytest>=7.4.0`, `oaklib>=0.6.0`.

**Decision: Replace `requirements.txt` in Phase 2.** Either delete it (forcing `pip install -e .[dev]` against `pyproject.toml`) or regenerate it from `pyproject.toml` via `pip-compile`. Until Phase 1.5 starts on the canonicalization mapping, keep the old `requirements.txt` around so anyone reproducing the legacy figures still has a working environment.

---

## 8. Summary table

| Artifact | Decision | Phase that touches it |
|---|---|---|
| `parse.py` | Archive | Phase 4 (after dashboard replaces it) |
| `testfile.py` | Retire | Phase 1 cleanup |
| `utils/test_indications.py` | Archive → replace with `tests/test_validation.py` | Phase 2 |
| `utils/pathtester.py` | Archive (after Phase-2 cross-check) | Phase 2 |
| `utils/json_yaml_convert.py` | Keep → move to `src/drugmechdb/io.py` | Phase 2 |
| `utils/build_indications.py` | Archive | Phase 4 |
| `utils/convert_to_biolink.py` | Retire | Phase 1 cleanup |
| `utils/xls_to_json.py` | Retire | Phase 1 cleanup |
| `utils/plot_paths.py` | Archive | Phase 4 |
| `utils/biolink_preds.txt` | Cross-check then archive | Phase 1.5 |
| `utils/dmdb_to_bl_map.csv` | Cross-check then archive | Phase 1.5 |
| `utils/deprecated_ids.txt` | Apply deletions, archive list | Phase 1 |
| `data_tools/` | Retire from runtime path | Phase 1 cleanup |
| `data_analysis/` | Archive (`attic/manuscript_2023/`) | Phase 1 cleanup |
| `scripts/split_monolith.py` | Keep, add `--check` mode | Phase 2 |
| `scripts/update_occurs_in_preserving_format.py` | Archive | Phase 1.5 |
| `requirements.txt` | Replace with `pyproject.toml`-driven flow | Phase 2 |

## 9. What Phase 1 does *not* change

To keep the Phase-1 surface area honest, this audit explicitly does **not**:
- Delete any of the files above. Decisions are recorded; moves happen in their respective phases.
- Create an `attic/` directory. That move should land alongside the first migration that needs it (Phase 1.5 is the natural moment).
- Touch `_layouts/`, `_includes/`, `pages/`, `_data/`, `css/`, `js/`, `fonts/`, `images/`. The Jekyll machinery is retired together with `parse.py` in Phase 4.

The single deliverable of Phase 1 §3.3 is this document plus the validation report in `docs/phase1_validation_report.md`.
