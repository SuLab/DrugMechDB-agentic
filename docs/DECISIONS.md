# Design decisions

An index of the decisions that shape this project: what was chosen, the main
alternative, and where the reasoning is recorded. The aim is that every choice can be
traced to its evidence. Where the rationale has not yet been written down, the row says
so rather than leaving the gap implicit.

## Data and format

| Decision | Chosen | Main alternative | Rationale recorded in |
|---|---|---|---|
| Storage unit | One YAML file per mechanism path under `kb/paths/`; the `indication_paths.*` monoliths are generated from them | One monolithic file, edited directly | Described in `docs/PRD_v3.md` §4.1; regeneration in `docs/PIPELINE.md`. **Why per-file was chosen is not yet written.** |
| Several mechanisms for one drug–disease pair | Separate files, suffixed `_1`, `_2`, … | Several paths inside one file | `docs/multipath_convention.md` |
| Record schema | LinkML (`MechanisticPath`) describing the existing format, with no data migration | A hand-written JSON Schema | Described in `docs/PRD_v3.md` §4.2. **Why LinkML was chosen is not yet written.** |
| Biolink version | New records pinned to Biolink 4.4.4, qualifiers included; legacy records keep their vocabulary until re-curated | Pin the old release, or migrate every stored record | `docs/biolink_version_decision.md` |
| Node names | Human-readable; identity is the CURIE, validated by type | Force the ontology's canonical label | `docs/node_name_convention.md` |

## Evidence

| Decision | Chosen | Main alternative | Rationale recorded in |
|---|---|---|---|
| What counts as a source | Source-agnostic: any fetched source that asserts the step, with the snippet verbatim in it | Secondary sources only (reviews, curated databases) | `AGENTS.md` §4 states the rule. **Why the policy changed is not yet written.** |
| Full text | Fetched only to locate and verify a snippet, deleted after QC; only the snippet and citation are committed | Commit open-access full text | `docs/evidence_license_scope.md` |
| Snippet verification | Exact substring of the cached source, normalised for whitespace, case and punctuation only | Semantic or fuzzy matching | `AGENTS.md` §0 and §4.1 |

## Validation

| Decision | Chosen | Main alternative | Rationale recorded in |
|---|---|---|---|
| Definition of a valid record | One QC gate (`scripts/qc.py`), the single source of truth; a `legacy` profile without the evidence layer, since legacy records carry no per-edge evidence | Separate validators per tool | `README.md`, `CLAUDE.md` |
| Which structural checks block | Four invariants a correct mechanism cannot violate (connectivity, cycle, duplicate edge, clinical shortcut); all other checks advisory | Block on every structural check | `scripts/quality/structural_quality.py` (module docstring); worksheet in `docs/structural_precision_audit.md` |
| Term existence | Resolve identifiers against their source ontology (OAK where available, otherwise OLS4 and source REST APIs), cached | A normalisation service such as Node Normalizer | `scripts/term_validation/__init__.py`. **Why not Node Normalizer is not yet written.** |

## Curation

| Decision | Chosen | Main alternative | Rationale recorded in |
|---|---|---|---|
| What the curating agent can see | A fixed eight-tool interface with no read access to the knowledge base, enforced in code | Instruct the agent not to look | `scripts/curate_engine.py` (module docstring) |
| Checking the science | An independent semantic critic, run after the gate, that re-derives each edge from its own retrieval and reports problems without naming fixes | Human review of every record | `scripts/quality/critic.py` (module docstring); `docs/quality_system_design.md` |
| Critic independence | Separate context, prompts and retrieval, with cite-or-abstain grounding; the same model family as the curator | A different model family | `scripts/quality/critic.py`; commit `20ccb84` |
| Curation model | Claude Opus 4.8 | Claude Sonnet 4.6 | `docs/model_decision.md`, `docs/opus_vs_sonnet_quality.md` |
| Model providers | Anthropic models only | Several providers | Commit `20ccb84` records what was removed. **Why is not yet written.** |
| Prompt caching | Cache the static prefix and the growing conversation, in curator and critic | Cache the static prefix only | `scripts/curate_engine.py` (comment at the request); measurement in `experiments/caching_test/` |

## Open: rationale still to write

1. **One file per path** — why per-record files over the monolith (review granularity, diffs, per-record validation are the likely reasons, but they are not recorded).
2. **LinkML** — why LinkML over a hand-written JSON Schema.
3. **Source-agnostic evidence** — what drove the change from secondary-only sourcing, and what protects against reconstructing a mechanism from primary findings that no source asserts.
4. **Term existence without Node Normalizer** — why resolving against each source ontology was preferred.
5. **Anthropic-only** — why a single provider, and what that costs in independence between curator and critic.
