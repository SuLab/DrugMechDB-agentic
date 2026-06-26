# CLAUDE.md — DrugMechDB AI-curation harness

> Orientation for agents working in this repo. It indexes the **machinery**; the
> **curation rules** live in `AGENTS.md` (the contract) and `CurationGuide.md` (the
> detailed guide) — this file points at them rather than repeating them.

## What this repo is

DrugMechDB as a **living, self-validating knowledge base**: 4,846 per-record path files
under `kb/paths/`, each a directed drug→…→disease mechanism graph, guarded by a 4-layer
QC gate and an agentic harness modeled on Monarch's Dismech. Work happens on the main
development branch. Changes are **additive and format-compatible** — this is meant to
become the official next-generation DrugMechDB.

## A record (the data)

`kb/paths/{drugbank}_{disease_mesh}_{n}.yaml` — keys: `directed`, `multigraph`, `graph`
(indication metadata + `_id`), `nodes` (`id` CURIE / `label` Biolink type / `name`),
`links` (edges: `key` predicate / `source` / `target`, joined by CURIE), `references`.
Edges may carry per-edge `evidence` (an `EvidenceItem` with a verbatim PubMed `snippet`).
`_index.yaml` is a **generated** aggregate — don't hand-edit it.

Full structure, the 14 node types, the 67-predicate vocabulary, and the path-quality
conventions are in **`AGENTS.md`** and **`CurationGuide.md`**. Read those before curating.

## The QC gate (`scripts/qc.py`)

The single source of truth for "is this record valid." It picks a **profile** per file
and runs the matching layers:

| Profile      | When                         | Layers      |
|--------------|------------------------------|-------------|
| `legacy`     | no per-edge evidence          | 1, 2, 3     |
| `ai_curated` | any edge has `evidence:`      | 1, 2, 3, 4  |

1. **schema** (LinkML `MechanisticPath`) · 2. **node ontology** (prefix↔label) ·
3. **predicate enum** (67 Biolink predicates) · 4. **reference** (snippet verbatim in source).

```bash
just qc                       # whole corpus, auto profile
just qc kb/paths/<file>.yaml  # one record
just qc-layer N <file>        # isolate one layer
just qc-json <file>           # machine-readable
```
Exit: 0 pass · 1 fail · 2 no files. (Bootstrap: `pip install -e ".[dev]"` into
`.venv-py310/` — gitignored, see the `justfile` header.)

## The self-validating property (pre-edit hook)

`.claude/hooks/validate_path_hook.py` runs as a **PreToolUse** hook on Edit/Write/MultiEdit.
It simulates the post-edit content of any `kb/paths/*.yaml` and runs the QC gate
(`--offline`) against it **before the write lands**; a validation failure (qc exit 1)
**blocks the edit** (hook exit 2) with the failing-layer report. It **fails open with a
warning** if `.venv-py310` isn't bootstrapped, so a fresh clone isn't bricked. Wiring is in
`.claude/settings.json`.

## Skills (`.claude/skills/`)

Invoke the one matching the task:
- **dmdb-compliance** — run/read the QC gate; diagnose which layer failed; judge keepability.
- **dmdb-terms** — node ontology ids + canonical labels (Layer 2; OAK / `ols-mcp`).
- **dmdb-references** — per-edge evidence; verbatim-snippet contract (Layer 4).
- **dmdb-pr-review** — review a path PR (QC, path quality, sourcing, diff hygiene).

## Commands (`.claude/commands/`)

- **/curate** `<Drug> for <Disease> [using <provider>]` — curate a new path.
- **/backfill** `<path-file or _id>` — add PubMed evidence to an existing path.
- **/create-pr** — validate, scope, branch, and open a PR for path work.

## MCP (`.claude/.mcp.json`)

- **ols-mcp** — interactive ontology search (complements OAK for Layer-2 term work).
- **pubmed** — fetch/verify PubMed for evidence (Layer-4 snippets).

## Sourcing boundary (hard rule)

Curate only **established, already-asserted** mechanisms from **secondary sources that
assert them** (DrugBank MoA, GO, UniProt, Reactome, reviews). **No primary/experimental-
literature reconstruction. No predicted/model-generated mechanism is ever a curation
input.** The evidence machinery is source-agnostic; the *which-sources* policy is still
being settled (PubMed-only vs. secondary-assertion) — see the sourcing policy in
`AGENTS.md` and confirm before a large run.

## Git / PR practice

Work on a feature branch off the main development branch; never commit path work directly
to the shared branch and never force-push it. Use **targeted `git add`** (the record, its
`references_cache/PMID_*.md`, optional `research/*.md`) — never `git add -A`. Re-run
`just qc` before opening a PR; CI enforces the same gate. Confirm the PR base branch with
the maintainers.
