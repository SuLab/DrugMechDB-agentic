---
description: Curate a new DrugMechDB mechanistic path for a (Drug, Disease) pair. Optionally seed with an external research agent.
argument-hint: <Drug> for <Disease> [using <provider>]
allowed-tools: Read, Edit, Write, Bash, Glob, Grep
---

# /curate — Curate a new DrugMechDB mechanistic path

**You are curating a single new mechanistic path connecting `$ARGUMENTS` in DrugMechDB.** The output is one YAML file under `kb/paths/` that passes all four QC layers under the `ai_curated` profile.

**Before doing anything else, read `AGENTS.md`** at the repo root. It defines the schema contract, ontology table, predicate vocabulary, evidence rules, and tool surface limits. The instructions below are a workflow on top of those rules — when in doubt, the rules in AGENTS.md win.

## Workflow

Follow these steps in order. Don't skip steps.

### 1. Parse the request

The invocation has two shapes:

- `/curate <Drug> for <Disease>` — direct PubMed-only curation. Skip step 4 (research provider).
- `/curate <Drug> for <Disease> using <provider>` — seed the curation with an external research agent before hitting PubMed. `<provider>` is one of the names returned by `python scripts/research.py list`. Currently implemented: `claude`, `openai`. Stubs (raise NotImplementedError when invoked): `perplexity`, `asta`.

Extract `Drug`, `Disease`, and `<provider>` (if given). Print all three back so the user can correct typos before you spend tokens.

### 2. Resolve identifiers

- Drug → look up DrugBank ID (`DB:DB…`) and MESH ID (`MESH:D…` or `MESH:C…`). At least one must be available; both is better. Search `kb/paths/_index.yaml` first — if the drug is already in DrugMechDB, the IDs are right there.
- Disease → MESH ID (`MESH:D…`). MONDO is not yet wired in v3.

If you can't find either drug ID or the disease MESH, stop and ask the user.

### 3. Pick the file index

```
grep -l "_{drugbank}_{disease_mesh}_" kb/paths/ 2>/dev/null | wc -l
```

If existing siblings are `_1`, `_2`, your new file is the next free index.

Path filename: `kb/paths/{drugbank_id}_{disease_mesh}_{N}.yaml`, e.g. `kb/paths/DB00945_MESH_D009203_3.yaml`. The graph `_id` matches the filename stem.

### 4. (Optional) Run the external research agent

**Skip this step if the user did not specify `using <provider>`.**

If a provider was specified, run it now to seed step 5 with candidate PMIDs and a proposed mechanism topology:

```
.venv-py310/bin/python scripts/research.py run {provider} "{Drug}" "{Disease}"
```

The script writes a dossier to `research/{drug_slug}_{disease_slug}-{provider}.md` and prints the cached/fetched status. If a fresh cached dossier already exists (default TTL: 30 days), the run is a no-op and exits cleanly — that is the expected behavior, not an error.

If the script reports `ERROR` (missing env var, unimplemented stub, network failure), surface that to the user and either:
- Stop and ask whether to proceed without external research, or
- Fall back automatically by treating step 4 as skipped (your judgment; favor stopping if the user explicitly requested a specific provider).

**Read the dossier.** The frontmatter's `candidate_pmids` list is the starting set for step 5. The body's "Proposed mechanism summary" and "Mechanism graph proposal (advisory)" sections give topology hints — but they are **advisory only**.

**The hard contract:** snippets in the dossier are NOT trustworthy. They were produced by an external agent that may paraphrase, summarize, or hallucinate. The only acceptable source for an `EvidenceItem.snippet` is the cached PubMed abstract fetched in step 5. If the dossier says PMID:23422285 contains the sentence "X acetylates COX-1", you must still fetch PMID:23422285 via `pubmed_fetch.py` and locate that exact sentence in the cached abstract before using it. If the sentence isn't there verbatim, find a different sentence (or a different PMID).

### 5. Fetch PMID abstracts via PubMed

Use the `scripts/pubmed_fetch.py` wrapper — this is the **only** sanctioned external source for evidence in v3, regardless of whether step 4 ran.

If step 4 produced a dossier, start with the PMIDs it proposed:

```
.venv-py310/bin/python scripts/pubmed_fetch.py fetch PMID:xxx PMID:yyy …
```

Then expand with your own searches if the dossier's set is too narrow:

```
.venv-py310/bin/python scripts/pubmed_fetch.py search "{drug} {disease} mechanism" --max 30
```

If step 4 was skipped, run the search step yourself and pick 5–15 PMIDs that look mechanism-focused (avoid clinical trial outcome papers unless they describe MOA), then fetch them.

Abstracts land in `references_cache/PMID_*.md`. **Read each one fully** before drafting — extracting the right verbatim snippet later depends on having the abstract in your context now. Drop dossier-proposed PMIDs that turn out to be irrelevant or unsupportive after you read them; the dossier is not authoritative.

### 5.5 Escalate to full text only when an abstract is insufficient

For an edge where no cached **abstract** has a verbatim supporting sentence, decide — per edge — whether to read full text. Don't read full text by default; it's slower and usually unnecessary.

1. **Is the paper on-topic for this edge?** If the abstract shows the paper isn't about this step, pick a different PMID instead of reading its body.
2. **Is open-access full text available?** Cheap check, no download:
   ```
   .venv-py310/bin/python scripts/pubmed_fetch.py probe PMID:xxx --json
   ```
   `fulltext_available: true` → escalate. `error:` set → unknown (network), retry. Otherwise stay on the abstract.
3. **Escalate (on-topic AND available):**
   ```
   .venv-py310/bin/python scripts/pubmed_fetch.py fetch PMID:xxx --fulltext
   ```
   This upgrades `references_cache/PMID_xxx.md` to `content_type: full_text` (abstract prepended). Re-read it, then snippet from the body. Cap with `--max-fulltext N` so you don't over-read.
4. If full text still has no verbatim supporting sentence, record `NO_EVIDENCE` or drop the edge — never paraphrase.

See AGENTS.md §4.4 for the `...`/`[...]` operators and the read-the-context guards (negation, wrong-drug, no bibliography matches).

### 6. Draft the path YAML

- Start the path at the drug node (`label: Drug`, prefix `MESH` or `DB`).
- Walk through 2–6 intermediate biological entities (proteins, pathways, processes, phenotypes) toward the disease node (`label: Disease`, prefix `MESH`).
- If step 4 ran, the dossier's mechanism graph proposal can suggest topology, but verify each step against an actual cached abstract before committing it. If a proposed edge can't be supported by a verbatim snippet, drop or reshape it.
- Each edge:
  - `key`: pick from the canonical 67 in `src/drugmechdb/schema/biolink_predicates.yaml`.
  - `evidence`: ≥1 `EvidenceItem` with:
    - `reference: PMID:xxxxxxxx`
    - `snippet:` **verbatim** substring of the cached source (abstract, or full text if you escalated in step 5.5) — copy/paste from `references_cache/`, never from the dossier.
    - `supports: SUPPORT` (the default) or `PARTIAL` if the abstract is about a closely-related-but-different claim.
    - `evidence_source: HUMAN_CLINICAL | MODEL_ORGANISM | IN_VITRO | COMPUTATIONAL | OTHER` — describes the cited paper's methodology, not yours.

If you can't find a verbatim sentence for an edge, **drop the edge** (or pick a different intermediate node whose evidence you do have).

### 7. Canonicalize predicates

```
.venv-py310/bin/python scripts/canonicalize_predicates.py --write {your_file}
```

Idempotent. Lowercases, strips `biolink:` prefixes, replaces underscores with spaces.

### 8. Run QC under ai_curated

```
.venv-py310/bin/python scripts/qc.py --profile ai_curated {your_file}
```

All four layers must pass:

- **Layer 1** (schema) — required fields present, types correct
- **Layer 2** (node ontology) — every CURIE prefix matches its node label
- **Layer 3** (predicate) — every edge key is in the enum
- **Layer 4** (reference) — every snippet is verbatim in the cached abstract

### 9. Iterate up to 3 times

If any layer fails, look at the report, fix, and re-run. Maximum **3 retries** per AGENTS.md §5.

If you exhaust the budget, write the final state of the file anyway and report **explicitly** in your summary:

> Unresolved validation failures after 3 retries: Layer N — {error}

The user / curator decides whether to merge or fix manually.

### 10. Report back

Final message to the user must include:

- Path file written: `kb/paths/...`
- Number of nodes, edges, and distinct PMIDs cited
- Final QC result per layer
- Retry count
- **Research provider used** (if any) — and of the dossier's candidate PMIDs, how many were ultimately cited vs. dropped. This is how we measure provider quality over time.
- If any layer is still failing: which layer, what error, what you tried

## Constraints

- File writes: `kb/paths/`, `references_cache/`, and `research/` only. **Don't** modify the schema, scripts, or other paths.
- Bash: only the commands listed in AGENTS.md §6 (which includes `scripts/research.py`).
- Network: PubMed abstracts + open-access full text via `scripts/pubmed_fetch.py` (it contacts NCBI, Europe PMC, and PubTator3 — see AGENTS.md §6). External research providers via `scripts/research.py` (provider-specific API calls, only when explicitly invoked). **No WebFetch** to arbitrary domains.
- The research dossier is **advisory**. Snippets, claims, and PMIDs from the dossier are all unverified until you confirm them against the cached PubMed abstract. Treat the dossier the way a careful reviewer treats a literature search result, not the way a citation manager treats a curated entry.
- If you find yourself wanting to paraphrase an abstract sentence to make a snippet "cleaner," stop — pick a different sentence instead. Layer 4 will reject paraphrases.
