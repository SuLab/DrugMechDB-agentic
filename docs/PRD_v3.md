# Product Requirements Document (PRD)
## DrugMechDB AI Curation Platform
**Version 3.0 — May 2026**

---

## 1. Product Overview

**Project Name:** DrugMechDB AI Curation Platform

**Target Outcome:** Upgrade the DrugMechDB repository by introducing an automated, agentic AI curation pipeline modeled on the DisMech project's architecture. This transforms manual curation into an AI-assisted workflow where contributors can request mechanistic path curation via natural language commands.

> **v2 Note (retained):** DisMech serves as the architectural inspiration for validation patterns and agent workflows. However, DrugMechDB's data model — Biolink-compliant directed graphs of drug→mechanism→disease traversal paths — is fundamentally different from DisMech's disease pathophysiology representation. The schema, YAML structure, and agent prompts must be designed for DrugMechDB's domain, not copied verbatim from DisMech.

> **v3 Note:** v2 framed the data split, schema, and predicate vocabulary as upcoming work. As of May 2026, the monolith split, the LinkML schema, the Biolink node enum, and the Biolink predicate vocabulary already exist in the repository (see §3.1). v3 documents the current state honestly and confines Phase 1 to remaining gaps. v3 also syncs the PRD's evidence model with the richer schema already on disk, defines the legacy-vs-ai_curated CI profile split, and adds previously missing sections (Out-of-Scope, Risks, Governance, Agent Mechanics).

---

## 2. Objectives & Success Metrics

- **Objective 1 — Accelerate Curation:** Reduce the median time to produce a validated mechanistic path from "hours of curator effort" to "minutes of agent runtime plus brief human review."
- **Objective 2 — Enforce High-Fidelity Evidence:** Prevent AI hallucinations by requiring verbatim PubMed abstract snippets for every edge in a mechanistic path produced through the AI pipeline.
- **Objective 3 — Ensure Semantic Accuracy:** Automate Biolink Model compliance for node ontology bindings (GO, MESH, HP, UniProt, etc.) and edge predicate validation against the Biolink predicate vocabulary.

**Baselines and KPIs:**

| KPI | Baseline (May 2026) | Target | When |
|---|---|---|---|
| New paths added per month | ~5–10 (manual curation, last 6 months) | ≥5× baseline (~25–50/month) | 6 months post-launch |
| AI-generated PRs passing **first-pass** validation (no human-applied fixes) | n/a | ≥80% | End of Phase 3 |
| Legacy paths with ≥1 evidence item per edge | 0 / 4,846 (0.0%) | ≥50% | 6 months post-launch |
| Median curator review time per AI-generated PR | n/a | <15 min | 3 months post-launch |
| First-pass validation rate maintained across all AI-generated PRs (rolling 30-day) | n/a | ≥80% | Ongoing |

The "5×" target is a directional north star, not a contract — adjust after the first month of real throughput data.

---

## 3. Current State Assessment

### 3.1 What already exists in `DrugMechDB/`

Phase 1 of v2 is partially complete. Inventory:

| Artifact | Path | Status |
|---|---|---|
| Monolith YAML | `indication_paths.yaml` (~272K lines) | Present; **do not delete** until backfill is complete |
| Split path files | `kb/paths/{drugbank_id}_{disease_mesh}_{index}.yaml` | **4,846 files** present |
| Path index | `kb/paths/_index.yaml` | Present |
| Monolith → per-file split script | `scripts/split_monolith.py` | Present |
| LinkML schema | `src/drugmechdb/schema/drugmechdb.yaml` | Present — defines `MechanisticPath`, `PathMetadata`, `PathNode`, `PathEdge`, `EvidenceItem` |
| Biolink node enum | `src/drugmechdb/schema/biolink_nodes.yaml` | Present (`BiolinkNodeType`) |
| Biolink predicate vocabulary | `src/drugmechdb/schema/biolink_predicates.yaml` | Present (`BiolinkPredicate` enum with usage-frequency comments) |
| `parse.py`, `testfile.py`, `data_tools/`, `scripts/` | repo root | Present — see §3.3 audit checklist |

**Evidence coverage today:** 0 of 4,846 paths contain any `evidence` field. Every edge currently asserts a relationship without a citation. Closing this gap is the central product problem v3 solves.

### 3.2 What is missing

| Missing artifact | Will be created in |
|---|---|
| `AGENTS.md` (curator-agent rules) | Phase 3 |
| `justfile` with a `just qc` target | Phase 2 |
| `scripts/validate_predicates.py` | Phase 2 |
| `scripts/canonicalize_predicates.py` + `data/predicate_aliases.yaml` | Phase 1.5 |
| `scripts/build_dashboard.py` + `docs/qc/index.html` | Phase 4 |
| `references_cache/` and PubMed snippet validator wiring | Phase 2 |
| GitHub Actions workflow for `just qc` on PRs | Phase 4 |
| `kb/paths/_backfill_status.yaml` | Phase 4 |
| Two CI validation profiles (`legacy`, `ai_curated`) | Phase 2 |

### 3.3 Audit checklist for existing tooling

Before writing replacements, answer these specific questions:

1. **`parse.py`** — does it already convert YAML↔JSON, and does it handle the per-file `kb/paths/` layout?
2. **`testfile.py`** — does the existing test suite cover any of the four planned validation layers? Migrate compatible tests into the new pytest layout under `tests/`.
3. **`data_tools/`** — list each script, its inputs/outputs, and whether it is still called. Retire scripts with no callers.
4. **`scripts/`** — `split_monolith.py` and `update_occurs_in_preserving_format.py` exist. Document what each does and whether they are still needed post-split.
5. **`requirements.txt`** — pin versions and add `linkml`, `linkml-runtime`, `linkml-validator`, `biolink-model`, `requests`, `pytest` if not already present.

Each answer should be recorded in a short `docs/tooling_audit.md`, not in this PRD.

---

## 4. Data Architecture

### 4.1 Modular File Storage (already implemented)

The monolith has been split into one file per path under `kb/paths/`, using `{drugbank_id}_{disease_mesh}_{index}.yaml` (e.g., `kb/paths/DB00619_MESH_D015464_1.yaml`). Multi-path drug-disease pairs (`_1`, `_2`, …) are stored as separate files. `kb/paths/_index.yaml` provides `_id → filename` lookup.

**Remaining Phase 1 work:**
- Run schema validation against all 4,846 files; produce a structural-failure report (file path + failing slot).
- Decide and document the convention for multi-mechanism cases (see §7 Open Q #2). The current convention — separate files per mechanism — is the working default unless a curator override is provided.
- Confirm `multigraph: true` semantics (see §4.4).

### 4.2 LinkML Schema (already implemented — synced documentation)

The schema lives at `src/drugmechdb/schema/drugmechdb.yaml`. Reference it directly; the descriptions below summarize the contract but the schema is the source of truth.

**Top-level: `MechanisticPath`** — graph metadata, nodes, links, optional references and comments. Requires `nodes` (≥2) and `links` (≥1).

**`PathMetadata`** — `path_id` (alias `_id`, format `{DrugBankID}_{DiseaseMESH}_{index}`), `drug`, `drug_mesh`, `drugbank`, `disease`, `disease_mesh`. All required.

**`PathNode`** — `id` (ontology-bound CURIE), `name`, `label` (`BiolinkNodeType`), optional `alt_names`, `alt_ids`. `id` prefix must match the canonical ontology for `label`.

**`PathEdge`** — `source`, `target`, `key` (`BiolinkPredicate`), `evidence`. `evidence` is **optional at the schema level** to allow legacy paths to validate; the `ai_curated` CI profile makes it required (see §5.3.5).

**`EvidenceItem`** — the schema model is richer than v2 described:
- `reference` (PMID, required, pattern `^PMID:\d+$`)
- `snippet` (verbatim abstract substring, required)
- `supports` (required) — one of:
  - `SUPPORT` — directly supports the claim
  - `REFUTE` — directly contradicts the claim
  - `PARTIAL` — partially or indirectly supports
  - `NO_EVIDENCE` — citation does not contain relevant evidence
  - `WRONG_STATEMENT` — annotated claim contains a demonstrable factual error; cited evidence has the correct information
- `evidence_source` (required) — one of `HUMAN_CLINICAL`, `MODEL_ORGANISM`, `IN_VITRO`, `COMPUTATIONAL`, `OTHER`. Describes the publication's methodology, not the curation method.
- `explanation` (optional) — curator commentary

The `REFUTE` / `WRONG_STATEMENT` values are intentional: a curator (human or agent) must be able to record that a published paper contradicts what the database currently asserts. This is how factual corrections enter the system.

### 4.3 Node-label → ontology bindings

These are the canonical bindings; legacy prefixes (`taxonomy`, `reactome`, `Pfam`, `TIGR`) are accepted at schema level and flagged at term-validation time.

| Biolink Node Type | Ontology |
|---|---|
| Drug | MESH, DrugBank (DB) |
| Protein | UniProt |
| BiologicalProcess | GO |
| MolecularActivity | GO |
| CellularComponent | GO |
| Cell | CL |
| Pathway | Reactome (REACT) |
| Disease | MESH |
| PhenotypicFeature | HP |
| GrossAnatomicalStructure | UBERON |
| ChemicalSubstance | MESH, CHEBI |
| GeneFamily | InterPro |
| OrganismTaxon | NCBITaxon |
| MacromolecularComplex | PR |

### 4.4 Multigraph semantics

Path files set `multigraph: true`. The agreed semantics:

- Multiple edges between the same `(source, target)` pair are permitted **only when the `key` (predicate) differs**.
- A single edge with two distinct citations is represented as **one `PathEdge` with two `EvidenceItem`s in its `evidence` list**, not two parallel edges.
- Validators enforce this: duplicate `(source, target, key)` triples within one path are a Layer-1 failure.

---

## 5. Core Features

### 5.1 AI Agent Integration (Claude Code)

**Command:** `/curate [Drug] for [Disease]`

**Workflow:**
1. Resolve drug → DrugBank/MESH and disease → MESH/MONDO identifiers.
2. Research the mechanistic literature via PubMed.
3. Draft a Biolink-compliant path YAML with nodes, edges, and evidence items.
4. Run `just qc --profile ai_curated` locally inside the agent loop.
5. If validation passes, open a PR for human review. If it fails, the agent iterates (bounded by a retry budget — see §5.1.3) and surfaces any unresolved failures in the PR description.

**Agent constraints** (canonical source: `AGENTS.md`, to be authored in Phase 3):
- All edge `key` values must be drawn from the `BiolinkPredicate` enum.
- All node IDs must use the canonical ontology for their node type (§4.3).
- Every edge in an AI-curated path must have ≥1 `EvidenceItem`.
- Snippets must be exact substrings of the cited PubMed abstract — no paraphrasing, no ellipses, no normalization.

#### 5.1.1 Agent mechanics

- The skill is implemented as a Claude Code slash command (`/curate`) backed by a skill markdown file under `.claude/commands/`.
- Tool surface granted to the agent:
  - File read/write scoped to `kb/paths/`, `src/drugmechdb/schema/`, and `references_cache/`.
  - Shell access limited to `just qc`, `linkml-validate`, `python scripts/validate_predicates.py`, and `python scripts/canonicalize_predicates.py --dry-run`.
  - HTTP access to `eutils.ncbi.nlm.nih.gov` via a thin wrapper (`scripts/pubmed_fetch.py`) that respects rate limits and writes to `references_cache/`.
- The agent is not granted network access to arbitrary domains; PubMed is the only sanctioned external source for evidence in v3.

#### 5.1.2 PubMed access policy

- Default to NCBI E-utilities with a registered API key (target ≥10 req/sec rate ceiling).
- Cache abstracts in `references_cache/PMID_xxxxxxxx.json` keyed by PMID. Cache entries include a fetched-at timestamp.
- Re-fetch policy: invalidate cache entries older than 90 days during the next access; always re-fetch entries flagged in NCBI's retraction feed.
- Paywalled PMIDs with no abstract available: the agent records `evidence_source: OTHER` with an `explanation` noting the access constraint and the edge is held back from the AI-curated profile (treated as missing evidence).

#### 5.1.3 Retry and surfacing

- The agent's per-path retry budget is 3 internal validation loops before opening a PR.
- If retries exceed the budget, the agent still opens the PR but flags unresolved failures in the PR body under a `## Unresolved validation failures` heading so reviewers can decide whether to fix or close.

### 5.2 Evidence Backfill Plan

The current database has **4,846 paths with zero evidence**. Backfill is a required workstream that runs in parallel with new curation.

1. **Automated backfill agent:** For each existing path, the agent finds PubMed support for each edge and proposes evidence annotations via PR. Source of truth for batches: `kb/paths/_backfill_status.yaml`.
2. **Priority ordering:**
   - Tier A: paths in the top 10% by downstream citation count (where measurable) or by appearance in user-reported issues.
   - Tier B: paths whose source drug is FDA-approved and currently in clinical use.
   - Tier C: everything else.
3. **Status tracking** in `kb/paths/_backfill_status.yaml`: `pending` | `in_progress` | `proposed` | `complete` | `held` per path. `held` is for paths where the agent could not find adequate evidence and a human curator must triage.
4. **Human sign-off:** Backfill PRs require curator approval (see §8 Governance). The agent proposes; a curator approves or revises.
5. **KPI:** ≥50% of paths reach `complete` within 6 months of platform launch; the dashboard tracks weekly progress.

### 5.3 Automated Validation Pipeline

Validation runs on every PR via GitHub Actions and locally via `just qc`. Four validation layers, plus a CI profile selector.

#### 5.3.1 Layer 1 — Schema validation
`linkml-validate` checks YAML structure against `drugmechdb.yaml`. Catches missing required fields, wrong types, malformed CURIEs, and duplicate `(source, target, key)` edges within a path.

#### 5.3.2 Layer 2 — Node ontology check
`linkml-term-validator` verifies that node IDs exist in the correct ontology for the declared `label` and that `name` matches the canonical ontology label. Catches hallucinated IDs, deprecated identifiers, and label drift.

#### 5.3.3 Layer 3 — Biolink predicate validation
`scripts/validate_predicates.py` checks every edge `key` against `biolink_predicates.yaml`. Rejects any predicate not in the controlled list. This depends on Phase 1.5 canonicalization completing first (see §6).

#### 5.3.4 Layer 4 — Reference verification
`linkml-reference-validator` resolves each PMID via PubMed E-utilities, extracts the abstract, and checks that `snippet` is a verbatim substring (whitespace-normalized, but no paraphrasing). Abstracts are cached in `references_cache/`. Fallback policy: if PubMed is unreachable, the layer emits a soft warning rather than a hard failure for already-cached PMIDs, and a hard failure for uncached PMIDs.

#### 5.3.5 CI profiles

Validation runs under one of two profiles, selected per-file or per-PR:

| Profile | Layers run | Evidence required per edge | Used for |
|---|---|---|---|
| `legacy` | 1, 2, 3 | No | Pre-existing paths during the grace period |
| `ai_curated` | 1, 2, 3, 4 | Yes (≥1) | All new paths from AI pipeline; all backfilled paths after approval |

Profile is determined by:
1. Explicit front-matter override in the PR body (`Profile: ai_curated`), if present.
2. Otherwise, presence of any `evidence` field in the file → `ai_curated`; absence → `legacy`.

This is the mechanical resolution of v2 Open Question #1 — see §7 for the policy framing.

### 5.4 Biolink Predicate Vocabulary (already defined)

Canonical location: **`src/drugmechdb/schema/biolink_predicates.yaml`** (note: this corrects the v2 path of `src/drugmechdb/predicates.yaml`, which never existed). The file defines the `BiolinkPredicate` LinkML enum, with each value carrying a `meaning:` mapping to the Biolink Model IRI and a usage-frequency comment from the existing corpus.

Layer 3 reads this enum directly; there is no separate predicate list to maintain.

### 5.5 QC Dashboard

A static HTML dashboard at `docs/qc/index.html`, generated by `scripts/build_dashboard.py`. Regeneration:
- On every merge to `main` (via GitHub Actions).
- Nightly at 06:00 UTC via a scheduled workflow, to pick up cache and ontology updates.
- Deployed to GitHub Pages.

**Panels:**
- **Coverage:** total paths, paths with ≥1 evidence item per edge, fully evidenced paths.
- **Backfill progress:** % by tier (A/B/C) and by drug class.
- **Ontology health:** % of nodes with valid ontology IDs, by node type. Flags deprecated IDs.
- **Predicate distribution:** frequency chart of edge `key` values; highlights any keys not in the enum (should be zero after Phase 2).
- **Priority targets:** ranked list of paths needing backfill, sourced from `_backfill_status.yaml` joined with tier metadata.

> **v2 Note (retained):** Meaningful QC metrics for DrugMechDB differ from DisMech. Focus on path-level evidence density and predicate health, not slot-coverage percentages.

---

## 6. Implementation Phases

### Phase 1: Audit & Schema Validation of Existing Split *(small — most of the v2 work is already done)*
- Produce the `docs/tooling_audit.md` answering §3.3.
- Run `linkml-validate` against all 4,846 files; produce a structural-failure report.
- Resolve any structural failures (rename slots, fix prefixes, etc.) so 100% of files pass Layer 1.
- Confirm or update multi-path-per-file convention (§7 Open Q #2).

**Exit criteria:** All 4,846 path files pass Layer-1 schema validation under the `legacy` profile.

### Phase 1.5: Predicate Canonicalization *(prerequisite for Phase 2 Layer 3)*
- Survey all distinct `key` strings across the corpus.
- Build `data/predicate_aliases.yaml` mapping legacy/informal predicates to the canonical Biolink predicates already enumerated in `biolink_predicates.yaml`.
- Implement `scripts/canonicalize_predicates.py` (idempotent, dry-run by default) and run it against all path files; commit the rewrite.
- Any predicate that cannot be mapped is escalated to a curator for either (a) addition to the enum (justified by a Biolink Model citation) or (b) re-curation of the edge.

**Exit criteria:** 100% of edge `key` values across `kb/paths/` are members of `BiolinkPredicate`.

### Phase 2: Validation Tooling
- Create `justfile` with `qc`, `qc --profile legacy`, `qc --profile ai_curated`, and `qc <path>` targets.
- Implement `scripts/validate_predicates.py` (Layer 3) reading `biolink_predicates.yaml`.
- Wire up `linkml-term-validator` (Layer 2) for node ontology checks.
- Wire up `linkml-reference-validator` (Layer 4) for snippet verification, with PubMed caching to `references_cache/`.
- Implement the profile selector in `just qc`.
- Run all four layers under the `legacy` profile against existing paths; produce gap report.

**Exit criteria:** `just qc` runs all four layers locally with clear pass/fail output and honors the profile selector. Layer 3 passes for 100% of legacy files.

### Phase 3: Agent Prompts & Skills
- Write `AGENTS.md` with the Biolink-specific curation rules, the predicate vocabulary reference, the node-type→ontology mapping, and the snippet-verbatim contract.
- Implement `/curate [Drug] for [Disease]` as a Claude Code slash command per §5.1.1.
- Implement the evidence-backfill skill (different agent prompt; reuses the same tool surface).
- Test against a stratified sample of **≥30 drug–disease pairs** spanning ≥5 drug classes and ≥5 disease areas. Document the sample selection in `docs/phase3_eval.md`.

**Exit criteria:**
- AI-generated paths pass Layers 1–4 under `ai_curated` on first attempt for ≥80% of the 30-case eval set.
- Median curator time-to-review on the 30 cases is <15 minutes.

### Phase 4: CI/CD, Dashboard, and Backfill Launch
- GitHub Actions workflow: run `just qc` on all changed `kb/paths/*.yaml` files per PR with auto-detected profile.
- Block merge on any validation failure; provide a documented override (PR label `validation-override` + maintainer approval) for grace-period exceptions.
- Build and deploy QC dashboard.
- Launch backfill campaign using the evidence-backfill skill, prioritized by tier.

**Exit criteria:** All new PRs are automatically validated, dashboard is publicly accessible, backfill campaign is underway, and ≥10% of Tier-A paths have proposed evidence within 30 days of launch.

---

## 7. Open Questions

1. **Evidence requirement for legacy paths.** The PRD mechanically resolves the *enforcement* via the `legacy`/`ai_curated` CI profile (§5.3.5). The **policy question that remains**: how long is the grace period before the `legacy` profile is retired (and all paths must meet `ai_curated`)? Recommendation: 6 months post-launch, reviewed against the 50% backfill KPI.

2. **Multi-path drug-disease pairs.** Current convention is separate files (`_1`, `_2`, …). v3 keeps this as the default. The alternative — one file with multiple path objects — is rejected for v3 because it complicates per-file validation and PR review.

3. **New predicates discovered during canonicalization.** When a legacy edge uses a relationship that has no Biolink-vocabulary equivalent, who approves adding a new predicate to `biolink_predicates.yaml`? Proposed: same curator approval flow as evidence; require a citation to Biolink Model documentation.

4. **Multi-curator quorum for high-stakes edges.** Should `REFUTE` / `WRONG_STATEMENT` evidence require two human approvals rather than one, given they encode factual corrections? Decision needed before Phase 4 launch.

---

## 8. Governance & Human-in-the-loop

- **Curator roles:**
  - *Reviewer* — anyone with merge rights on `DrugMechDB`. Required for all AI-generated PRs.
  - *Domain curator* — a named subset of reviewers with biomedical curation expertise. Required for `REFUTE` / `WRONG_STATEMENT` evidence and for any addition to `biolink_predicates.yaml`.
- **Review SLA:** target 5 business days from PR open to first review for AI-generated PRs; tracked on the dashboard.
- **Disputes:** if a curator and the agent disagree on the correctness of an edge, the curator's decision is final; the agent's draft is preserved in the PR history but not merged. Disputes that recur for the same drug–disease pair are surfaced as a `held` status in `_backfill_status.yaml`.
- **Audit trail:** every AI-generated PR carries the agent invocation context (model, prompt version, retry count) in the PR body so reviews are reproducible.

---

## 9. Risks & Dependencies

| Risk / Dependency | Impact | Mitigation |
|---|---|---|
| PubMed E-utilities downtime or rate limiting | Layer 4 fails, agents block | Cache in `references_cache/`; soft-fail for cached PMIDs; backoff and retry in `pubmed_fetch.py` |
| Paper retractions or abstract edits cause silent snippet rot | Database accumulates stale "verbatim" snippets | Nightly cache invalidation for entries >90 days old; check NCBI retraction feed weekly; surface drift on the dashboard |
| Biolink Model version drift | Predicate enum becomes stale | Pin Biolink Model version in `requirements.txt`; document upgrade procedure in `docs/biolink_upgrade.md`; quarterly review |
| Paywalled PMIDs with no public abstract | Cannot verify snippets | Agent records `OTHER` evidence source with `explanation`; edge held back from `ai_curated` until alternative open citation is found |
| LLM API cost overruns during backfill | Backfill stalls | Per-PR cost telemetry; monthly cost cap configured per environment; backfill scheduled in budgeted batches |
| Ontology updates rename or deprecate IDs | Layer 2 starts failing previously valid paths | Pin ontology versions used by `linkml-term-validator`; semi-automated re-binding script for renames |
| Agent hallucination of plausible-looking PMIDs | Fabricated citations slip through | Layer 4 verifies snippet-in-abstract; PMID must resolve via E-utilities (not just be well-formed) |
| Agent submits a path that is biologically plausible but unsupported | Curator review fatigue | First-pass validation rate KPI; if rate drops below 80%, pause agent invocations and revise `AGENTS.md` |

---

## 10. Out of Scope (for v3)

The following are intentionally not pursued in this version and will be reconsidered in a future PRD:

- **Novel drug repurposing or discovery.** The platform curates known mechanisms; it does not propose new drug–disease pairs.
- **Contradiction resolution across conflicting publications.** When two papers disagree, both can be cited (`SUPPORT` and `REFUTE`); the platform does not attempt to adjudicate.
- **Off-label indication inference.** Off-label uses may be curated when explicitly requested, but the platform does not enumerate them automatically.
- **Disease-subtype or patient-subgroup modeling.** Paths are at the disease level; subgroup-specific mechanisms are out of scope.
- **Non-English literature.** PubMed English-language abstracts only.
- **Sources beyond PubMed.** Preprints (bioRxiv), textbooks, and curated databases (e.g., DrugBank prose) are not sanctioned evidence sources in v3.
- **Disease ontology re-mapping (MESH→MONDO).** Discussed but deferred; current MESH-based identifiers remain canonical.
- **Real-time interactive curation UI.** The interface is the Claude Code slash command and the resulting PR; no separate web UI in v3.

---

*Version 3.0 — May 2026. Supersedes v2.0 (April 2026).*
