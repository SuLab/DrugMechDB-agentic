# AGENTS.md — Curation rules for DrugMechDB AI agents

This file is the single source of truth for what an AI agent must do when curating or backfilling DrugMechDB mechanistic paths. The `/curate` and `/backfill` slash commands (under `.claude/commands/`) defer to the rules below — any divergence is a bug in those skills.

**Audience:** every Claude Code session invoking `/curate` or `/backfill`. Read this file in full before drafting any path YAML.

**PRD reference:** [PRD v3 §5.1](docs/PRD_v3.md)

---

## 0. The one rule that overrides every other rule

**Every edge in an AI-curated path must carry at least one `EvidenceItem` whose `snippet` is a verbatim substring of the cited source's cached text** — its PubMed **abstract** by default, or its **open-access full text** when you escalate (see §4.4). No paraphrasing. No fabrication. If you can't find a verbatim snippet in the cached source, you can't add the edge.

The matcher (`linkml-reference-validator`) normalizes whitespace, case, and punctuation before comparing and supports a `...` multi-part operator — treat that as a safety net for messy full-text prose, **not** a license to paraphrase (see §4.5).

If you find yourself rewording, summarizing, or "improving" a source sentence — stop. Pick a different sentence, or drop the edge.

**Corollary for external research providers.** When the `/curate` skill is invoked with `using <provider>` (see §5 step 3), the provider returns a *dossier* with proposed PMIDs and a narrative mechanism summary. The dossier is **advisory only**:
- Snippets the dossier quotes are NOT acceptable evidence sources. The only acceptable source for `EvidenceItem.snippet` is the PubMed-cached abstract written by `scripts/pubmed_fetch.py`.
- A PMID proposed by the dossier must still be fetched via `pubmed_fetch.py`. If the abstract does not contain a verbatim sentence supporting the edge, drop the PMID — even if the dossier quoted plausible-looking text.
- The dossier's mechanism graph proposal is a topology hint, not a contract. Every edge it proposes must be independently supported by a verbatim PubMed snippet, or it doesn't enter the path.

This split — provider proposes, PubMed verifies — is what lets the research agent operate with broad recall while the curation agent stays strictly faithful to source text.

---

## 1. What you're producing

A single YAML file under `kb/paths/{drugbank_id}_{disease_mesh}_{N}.yaml` (where `N` is the next available index for that drug-disease pair; check `kb/paths/_index.yaml` and existing siblings before picking).

The file conforms to the LinkML schema at `src/drugmechdb/schema/drugmechdb.yaml`, top class `MechanisticPath`. Read the schema if anything below conflicts with it — the schema wins.

### Skeleton

```yaml
directed: true
multigraph: true
graph:
  _id: {DrugBankID}_{DiseaseMESH}_{N}            # required, e.g. DB00945_MESH_D009203_1
  drug: aspirin                                   # required
  drug_mesh: MESH:D001241                         # optional but recommended
  drugbank: DB:DB00945                            # optional but recommended; at least one of drug_mesh / drugbank must be present
  disease: Myocardial infarction                  # required
  disease_mesh: MESH:D009203                      # required
nodes:                                            # ≥2 nodes
  - id: <ontology:id>
    name: <canonical name>
    label: <BiolinkNodeType>
  - ...
links:                                            # ≥1 edge
  - key: <BiolinkPredicate>                       # must be exact-match in biolink_predicates.yaml
    source: <node id>
    target: <node id>
    evidence:                                     # required for ai_curated; ≥1 item
      - reference: PMID:xxxxxxxx                  # required
        snippet: "Verbatim substring of the abstract."   # required, no quotes in YAML if avoidable
        supports: SUPPORT                         # required: SUPPORT | REFUTE | PARTIAL | NO_EVIDENCE | WRONG_STATEMENT
        evidence_source: HUMAN_CLINICAL           # required: HUMAN_CLINICAL | MODEL_ORGANISM | IN_VITRO | COMPUTATIONAL | OTHER
        explanation: "Optional curator commentary."  # optional
references:                                       # optional — secondary URLs (DrugBank, Wikipedia, etc.)
  - https://...
```

---

## 2. Node ontology table

The CURIE prefix of every node `id` **must** match the canonical ontology for that node's `label`. The validator (`scripts/validate_node_ontology.py`) rejects mismatches.

| Biolink `label` | Canonical ID prefix(es) | Legacy (tolerated, do not introduce) |
|---|---|---|
| `Drug` | `MESH`, `DB` | — |
| `Protein` | `UniProt` | — |
| `BiologicalProcess` | `GO` | — |
| `MolecularActivity` | `GO` | — |
| `CellularComponent` | `GO` | — |
| `Cell` | `CL` | — |
| `Pathway` | `REACT` | `reactome` |
| `Disease` | `MESH` | — |
| `PhenotypicFeature` | `HP` | — |
| `GrossAnatomicalStructure` | `UBERON` | — |
| `ChemicalSubstance` | `MESH`, `CHEBI` | — |
| `GeneFamily` | `InterPro` | `Pfam`, `TIGR` |
| `OrganismTaxon` | `NCBITaxon` | `taxonomy` |
| `MacromolecularComplex` | `PR` | — |

**Do not introduce legacy prefixes in new paths.** They exist only because of historical curation; new files must use the canonical prefix.

**Pick the label that fits the actual ontology of the ID, not what feels descriptive.** Concrete pitfalls — these have all appeared in the legacy corpus and are listed here so the agent doesn't repeat them:

- HPO IDs (`HP:xxxxxxx`) are phenotypes, not biological processes. `Tremor (HP:0001337)` → `PhenotypicFeature`, never `BiologicalProcess`.
- Reactome IDs (`R-HSA-…`) are pathways. `Prostaglandin Synthesis (REACT:R-HSA-2162123)` → `Pathway`, never `BiologicalProcess`.
- DrugBank IDs identify drugs. If you have a `DB:` ID, the label is `Drug` (unless DBMET, see below).
- DBMET IDs are DrugBank metabolites — currently outside the canonical set. If you need to cite one, escalate; do not paper over with the wrong label.

---

## 3. Predicate vocabulary

Every edge `key` must be an **exact** member of the `BiolinkPredicate` enum in `src/drugmechdb/schema/biolink_predicates.yaml` (67 predicates as of May 2026). The list includes the high-frequency ones the agent will reach for first:

```
positively regulates    negatively regulates    decreases activity of    increases activity of
positively correlated with    negatively correlated with    causes    contributes to
participates in    occurs in    located in    part of    manifestation of    in taxon
treats    prevents    has metabolite    binds    affects    disrupts    affects risk for
…
```

Read the file; the descriptions distinguish near-synonyms (e.g. `regulates` vs `positively regulates`, `correlated with` vs `causes`).

**You may emit predicates in casual surface forms** — `positively_regulates`, `biolink:positively_regulates`, `Positively Regulates` — and `scripts/canonicalize_predicates.py --write` will normalize them. But the **final** YAML must use the canonical form (lowercase, spaces, no prefix). Always canonicalize before validation.

**You may NOT invent new predicates.** If no canonical predicate fits, escalate per PRD §7 Open Q #3 (adding to the enum requires curator approval + Biolink Model citation).

---

## 4. Evidence rules

### 4.1 What counts as evidence

- A `PMID:xxxxxxxx` whose **abstract** appears in PubMed E-utilities (English language, public access).
- When the abstract is insufficient for an edge, the **open-access full text** of the same PMID, fetched via `pubmed_fetch.py fetch --fulltext` (see §4.4). Full text is pulled only from the redistribution-permissive PMC open-access subset.
- The `snippet` is a substring of the cached source under the matcher's normalization (whitespace/case/punctuation-tolerant, with an optional `...` multi-part operator). It does **not** accept paraphrases, summaries, or translations.

### 4.2 What does NOT count

- Preprints (bioRxiv, medRxiv) — out of scope in v3 (PRD §10).
- Textbooks, DrugBank prose, Wikipedia. Use `references:` for these as secondary context; don't promote them to `EvidenceItem.reference`.
- Paywalled papers whose abstract isn't published. Record `evidence_source: OTHER` with an `explanation` noting the access constraint and hold the edge back (don't include in the path); flag for curator.

### 4.3 Picking the right `supports` and `evidence_source`

| `supports` | When |
|---|---|
| `SUPPORT` | Abstract directly supports the edge claim (the default) |
| `PARTIAL` | Abstract supports a closely related claim but not the exact one (e.g. in a different tissue / species / dose) |
| `REFUTE` | Abstract directly contradicts the claim. Only use after curator confirmation that the database should record the contradiction. |
| `NO_EVIDENCE` | Cited reference does not actually contain evidence for this edge. **Don't add the edge.** This value exists for backfill correction. |
| `WRONG_STATEMENT` | The cited evidence shows the existing claim is factually wrong. Curator territory; do not introduce in `/curate`. |

| `evidence_source` | What kind of paper |
|---|---|
| `HUMAN_CLINICAL` | Patients, cohorts, case reports, RCTs, epidemiology |
| `MODEL_ORGANISM` | Mouse / rat / zebrafish / primate / veterinary in vivo |
| `IN_VITRO` | Cell culture, organoids, biochemical assays |
| `COMPUTATIONAL` | In silico, modelling, ML predictions |
| `OTHER` | Anything not fitting the above (also the slot for paywalled/no-abstract cases) |

If you can't tell, pick `OTHER` and put your reasoning in `explanation`.

### 4.4 Abstract-first; escalate to full text only when needed

Reading full text costs tokens and time, so **default to the abstract** and escalate per *edge*, not per paper:

1. **Try the abstract first.** If a verbatim sentence in the cached abstract supports the edge, use it — done.
2. **If not, triage before escalating** — two cheap checks decide whether full text is worth fetching:
   - *On-topic?* Is the paper actually about this edge (abstract discusses the drug/target/mechanism but doesn't state this specific step)? If it's simply the wrong source, **pick a different PMID** — don't read its body.
   - *Available?* `pubmed_fetch.py probe PMID:x --json` — one metadata call, no download. `fulltext_available: true` (open-access only) → escalate. If `error` is set, that's *unknown* (network) — retry, don't read it as "unavailable."
3. **Escalate only when on-topic AND available:** `pubmed_fetch.py fetch PMID:x --fulltext` upgrades that PMID's cache to `content_type: full_text` (abstract prepended). Re-read it and snippet from the body. `--max-fulltext N` caps escalations per run.
4. **If full text still doesn't support the edge**, record `NO_EVIDENCE` or drop it — never paraphrase.

**Operators (full text, sparingly).** When an unavoidable inline-citation artifact splits the sentence you want, the matcher's `...` quotes the two clean halves: `snippet: "aspirin acetylates ... cyclooxygenase 1"`; `[...]` drops an editorial insert. Prefer a single contiguous sentence when one exists.

**Read the context before accepting a full-text match.** A substring hit can land in a *negated/refuted* sentence (use `REFUTE`/`WRONG_STATEMENT`/`NO_EVIDENCE`, not `SUPPORT`) or in a sentence about a *different drug* in a multi-drug paper (confirm the subject is your entity). Bibliographies and raw table cells are excluded from the cached body, so a match won't come from a reference list.

**Sourcing note.** Escalation currently allows full text of *any* open-access article — broader than the conservative-sourcing rule (which favors secondary sources that *assert* an established mechanism); this policy is under review, so confirm with the maintainers before a large run. See the `dmdb-references` skill.

### 4.5 Snippet picking tactics

- Prefer the **shortest** verbatim sentence that supports the edge unambiguously.
- If the abstract uses the inverse phrasing (`X reduces activity of Y`), that supports a `decreases activity of` edge.
- Don't extract from the title alone — the cache stores both, but a sentence from the abstract body is more defensible.
- Avoid sentences that contain hedges (`may`, `suggests`, `appears to`) when a confident sentence is available.

---

## 5. Workflow (the only one)

The `/curate` and `/backfill` skills follow this exact sequence. Deviation is the most common source of validation failure.

1. **Resolve identifiers.**
   - Drug → DrugBank ID + MESH ID. If either is missing in PubChem/DrugBank, record what you found and proceed; the schema accepts one or the other.
   - Disease → MESH ID. MONDO is acceptable for future expansion but not yet wired in v3.

2. **Decide on the next file index.**
   ```
   grep -l "_{drugbank}_{disease_mesh}_" kb/paths/ | wc -l
   ```
   New file is `_N+1`.

3. **(Optional) Run the external research agent.**

   Skip this step if the user did not specify `using <provider>` on `/curate`.

   If a provider was specified, seed the curation with an external research agent:
   ```
   .venv-py310/bin/python scripts/research.py run <provider> "<Drug>" "<Disease>"
   ```
   The script writes a dossier to `research/<drug_slug>_<disease_slug>-<provider>.md` and prints cache or fetch status. A 30-day TTL applies; a fresh cached dossier short-circuits the API call.

   `python scripts/research.py list` shows registered providers and their env-var requirements. `claude` and `openai` are implemented; `perplexity` and `asta` are stubs that raise NotImplementedError. If the user requests an unimplemented provider, surface the error and ask whether to proceed without external research.

   **Read the dossier in full.** Its YAML frontmatter has a `candidate_pmids` list that seeds step 4 below. Its body contains a "Proposed mechanism summary" and a "Mechanism graph proposal (advisory)" — both are topology hints, not contracts. See §0 "Corollary for external research providers" for the advisory rule that governs every byte of dossier content.

4. **Research via PubMed.**
   - If step 3 ran, start by fetching the dossier's candidate PMIDs: `scripts/pubmed_fetch.py fetch PMID:xxx PMID:yyy …`. Then expand with your own searches if the dossier's set is too narrow.
   - If step 3 did not run, use `scripts/pubmed_fetch.py search "drug-name AND disease-name AND mechanism"` for an initial query, then fetch the candidates you pick.
   - In both cases, the cached abstracts under `references_cache/` are the sole acceptable source of verbatim snippets. PRD §10 limits sources to PubMed only.
   - Drop dossier-proposed PMIDs that turn out to be irrelevant or unsupportive after you read them; the dossier is not authoritative.

5. **Draft the path.**
   - Start from the canonical drug node (MESH or DB).
   - Walk through the mechanism to the disease (MESH).
   - Pick predicates from §3 only. When in doubt, pick the more general predicate (`regulates` over `positively regulates` if the directionality isn't clear in the cited sentence).
   - Match each edge to a snippet *while* drafting; don't add edges that lack a snippet.

6. **Canonicalize.**
   ```
   .venv-py310/bin/python scripts/canonicalize_predicates.py --write {your_file}
   ```
   Lowercases, strips `biolink:` prefixes, replaces underscores with spaces.

7. **Validate.**
   ```
   .venv-py310/bin/python scripts/qc.py --profile ai_curated {your_file}
   ```
   Or `just qc -- --profile ai_curated {your_file}` if `just` is installed.

8. **Iterate up to 3 times.** If validation fails, fix and re-run. If you've used all 3 retries:
   - Open a PR anyway (or save the file as draft) with a `## Unresolved validation failures` section in the description listing what's still failing.
   - This is the surfacing rule from PRD §5.1.3 — don't hide failures.

---

## 6. Tool surface (what the skill is allowed to use)

Granted (PRD §5.1.1, extended for Phase 4b research providers):

- **File read/write:** scoped to `kb/paths/`, `src/drugmechdb/schema/`, `references_cache/`, and `research/`. Read-only for `tests/`, `data/`, `docs/`. **Don't write anywhere else.** No new top-level directories.
- **Bash:** restricted to:
  - `just qc …` and `python scripts/qc.py …`
  - `python scripts/validate_*.py …`
  - `python scripts/canonicalize_predicates.py …`
  - `python scripts/pubmed_fetch.py …`
  - `python scripts/research.py …` — only when the user invoked `/curate` with `using <provider>`. Do not run research speculatively.
  - `linkml-validate …` for spot-checks
  - `git status` / `git diff` for awareness; do **not** run `git commit`, `git push`, or destructive git commands.
- **HTTP — direct from the curation agent:** only via the `pubmed_fetch.py` wrapper, the trusted boundary that rate-limits (per host) and writes the cache. The wrapper contacts `eutils.ncbi.nlm.nih.gov` (PubMed abstracts + efetch-pmc), `www.ebi.ac.uk` (Europe PMC full text + availability probe), and `www.ncbi.nlm.nih.gov` (PubTator3 full text). The agent never calls these hosts directly and never `WebFetch`es arbitrary domains — only the wrapper. The wrapper also writes `references_cache/`, which is **script-write-only** (a pre-edit hook blocks the agent from editing it), so the agent cannot author the source text Layer 4 trusts.
- **HTTP — via research providers:** `scripts/research.py` provides a separate, narrower allowance. When invoked with `using <provider>`, it makes provider-specific API calls (e.g. `api.anthropic.com` for `claude`, `api.openai.com` for `openai`) entirely encapsulated inside the script. The agent never sees the provider's HTTP endpoints directly; it only reads the dossier written to `research/`. This split means a future provider can be added without expanding the curation agent's network surface.

Not granted:

- WebSearch / WebFetch to non-PubMed domains from the curation agent itself
- Direct network calls outside the `pubmed_fetch.py` and `research.py` wrappers
- Running `scripts/research.py` when the user did not request a provider — research has a per-query cost and must be user-initiated
- Writing to test fixtures, schema files, or scripts (those are repository design surface; bring up requests with a maintainer)
- Removing or renaming existing paths under `kb/paths/`

---

## 7. Output expectations

When the skill completes successfully:

- **One new file** under `kb/paths/` per `/curate` invocation. (Or modifications to one existing file per `/backfill`.)
- **No untracked changes** to scripts, schema, or other paths.
- **A short status summary** printed back to the user including:
  - The path file written
  - The number of nodes and edges
  - The PMIDs cited
  - The QC layer-by-layer pass/fail result on the final run

If validation didn't pass on first attempt but did within the retry budget, mention that explicitly. If it failed all 3 retries, explain *why* (which layer, which check) so a curator can pick it up.

---

## 8. Anti-patterns observed in legacy corpus — don't repeat

- **Don't label HPO IDs as `BiologicalProcess`** (4 occurrences in legacy data; see Layer 2 gap report).
- **Don't label Reactome IDs as `BiologicalProcess`** (23 occurrences; they're pathways).
- **Don't label MESH disease IDs as `Protein` / `GeneFamily` / `PhenotypicFeature`** unless you've confirmed that's actually what the MESH descriptor refers to. Most cases are mis-bindings that need UniProt / InterPro / HP equivalents instead.
- **Don't write `drugbank: null` or `drug_mesh: null`.** Omit the field; the schema is now permissive (Phase 1 fix).
- **Don't paraphrase abstracts.** Don't do it.

---

*Last updated: May 2026 (Phase 3).*
