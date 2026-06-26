---
description: Backfill PubMed evidence onto an existing DrugMechDB path file.
argument-hint: <path-file or _id>
allowed-tools: Read, Edit, Bash, Glob, Grep
---

# /backfill — Add PubMed evidence to an existing DrugMechDB path

**You are annotating an existing legacy path with `EvidenceItem`s on each edge.** The path file already has nodes and edges; your job is to add `evidence:` blocks so every edge carries at least one verbatim PMID snippet.

**Read `AGENTS.md` first.** The schema contract, evidence rules, and tool surface limits there apply identically to `/backfill`. The only difference from `/curate` is that the nodes and edges are pre-existing — you don't draft them, you cite them.

## When to use this skill vs `/curate`

- `/curate Aspirin for Acute MI` — there is **no path yet** for this pair (or you want a new mechanism for a pair that already has one). You draft from scratch.
- `/backfill kb/paths/DB00945_MESH_D009203_1.yaml` — the **path exists** in legacy form. You find PubMed support for each edge as-is. Do not change predicates, node IDs, or topology.

If the existing edges are not actually supported by any PubMed evidence you can find, record `supports: NO_EVIDENCE` and flag the edge in your summary for curator triage. **Do not delete edges or change their `key`.**

## Workflow

### 1. Locate the target file

The argument is either a relative path (`kb/paths/...yaml`) or a bare `_id`. If it's an `_id`, resolve via:

```
grep -l "_id: {_id}" kb/paths/*.yaml
```

Read the file. Note the drug, disease, current edges, and any existing `references:` block.

### 2. Read existing references for context

If `references:` includes DrugBank or Wikipedia URLs, those are *not* evidence — they're secondary context. But the URLs may hint at which PubMed papers describe the mechanism (DrugBank's mechanism-of-action section often lists primary citations).

### 3. Research via PubMed

For each edge in the file, draft a focused query targeting the source-target relationship.

```
.venv-py310/bin/python scripts/pubmed_fetch.py search "{source_name} {target_name} {predicate}" --max 20
.venv-py310/bin/python scripts/pubmed_fetch.py fetch PMID:xxx ...
```

Read each fetched abstract. Find the **verbatim sentence** that supports this specific edge's claim. Copy it as-is.

### 3.5 Escalate to full text only when an abstract is insufficient

If an edge has no verbatim supporting sentence in any cached **abstract**, decide per edge whether to read full text (don't do it by default):

```
.venv-py310/bin/python scripts/pubmed_fetch.py probe PMID:xxx --json     # available? (no download)
.venv-py310/bin/python scripts/pubmed_fetch.py fetch PMID:xxx --fulltext # escalate if on-topic + available
```

`fetch --fulltext` upgrades the cache to `content_type: full_text` (abstract prepended); re-read it and snippet from the body. If full text still doesn't support the edge, use `NO_EVIDENCE` (step 5) — never paraphrase. See AGENTS.md §4.4.

### 4. Add evidence in place

Edit the file to add an `evidence:` list on each edge. Preserve all existing fields. Do not reorder or re-key. Each `EvidenceItem`:

```yaml
- reference: PMID:xxxxxxxx
  snippet: "<verbatim substring from cached source: abstract or full text>"
  supports: SUPPORT          # or PARTIAL, NO_EVIDENCE (see below)
  evidence_source: <bucket>
  explanation: ""            # optional curator note
```

### 5. Edges you can't support

If, after a reasonable search (≥10 PMIDs scanned for that specific edge), you find no abstract that supports the claim:

- Add an `EvidenceItem` with `supports: NO_EVIDENCE`, citing the most-relevant non-supporting paper. Include an `explanation` describing what you searched for and didn't find.
- This holds the edge back from the `ai_curated` profile until a curator decides.

Do **not**:

- Invent a supporting snippet by paraphrasing
- Delete the edge
- Change the predicate to make a weaker available citation fit

### 6. Canonicalize and validate

```
.venv-py310/bin/python scripts/canonicalize_predicates.py --write {file}
.venv-py310/bin/python scripts/qc.py --profile ai_curated {file}
```

Iterate up to 3 retries on failures.

### 7. Report

Final message must include:

- Number of edges in the file
- Number now carrying ≥1 `EvidenceItem` with `supports: SUPPORT` or `PARTIAL`
- Number flagged `NO_EVIDENCE` (these are the curator triage queue)
- Total distinct PMIDs cited
- Final QC result per layer
- Retry count

## Constraints

Same as `/curate` — see AGENTS.md §6. Additional rules specific to backfill:

- **Do not change `_id`, drug/disease MESH IDs, node IDs, node labels, edge `source`, edge `target`, or edge `key`.** These are pre-existing curator decisions. If you believe an edge is incorrectly modeled, surface that in your summary; do not silently fix it. Layer 2 / Layer 3 gaps inherited from legacy curation are out of scope for `/backfill`.
- **Do not delete existing fields**, even ones that look redundant (`directed`, `multigraph`, etc.).
- **If the file fails Layer 2 (e.g. wrong CURIE prefix on a node)**, that is a separate remediation track. Note it in your summary and proceed; backfill targets Layer 4.
