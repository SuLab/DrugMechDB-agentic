# Blinded judge harness (`scripts/run_blinded_judge.py`)

A thin orchestration layer over the existing semantic judge (`scripts/quality/judge/`)
for scoring a batch of curated paths — e.g. the output of a curation pilot or a
model-vs-model run. It runs the **edge-evidence judge** (Layer 5) and the
**path-coherence judge** (Layers 6/7) over each path and writes a results table
(JSON + Markdown). It does not reimplement judging: it calls `judge_edges` /
`judge_path` and reuses `quality_profile.edge_faithfulness` for the edge aggregate.

See `docs/path_quality_framework.md` §6 (grounding) and §7 (calibration) for why the
judge is qualified by grounding, not intelligence, and why calibration is still owed.

## What it produces

For each path (referenced by an anonymous **blind id**):

- the per-edge evidence aggregate — re-derived `SUPPORT` fraction, agreement with the
  curator's self-labels, flagged edges (from `edge_faithfulness`);
- the path-coherence verdict — `overall ∈ {accept, revise, reject, abstain}`, plus
  `mechanism_is_accepted`, `net_effect_correct`, `missing_step`, shortcut presence, and
  the curator-facing `issue_for_curator`;
- `gold_comparison` vs the legacy path, when one is resolvable (see below).

And a corpus aggregate: accept/revise/reject/abstain counts (overall and **per arm**),
the gold-comparison distribution, and **agreement-with-legacy** (the fraction of
paths-with-a-legacy the judge did not classify as `disagree`).

Two files land under `--out-dir`: `blinded_judge_results.json` (machine-readable, incl.
the reveal key + aggregate) and `blinded_judge_results.md` (the readable table).

## Blinding (framework §7)

The judge is never told which model produced which path.

1. The judge input is built by the existing `build_edge_inputs` / `build_path_input`
   functions, which pass only path *content* (nodes, predicates, evidence, and
   drug/disease/mesh) — never the record `_id`, the source directory, or a model tag.
2. Paths from all arms are pooled, shuffled under a fixed `--seed`, and given anonymous
   ids (`B001`, `B002`, …). The per-path results block is blind. The arm/source lives in
   a separate `reveal_key`, joined back only to compute the post-scoring aggregate. The
   per-path table shows `drug → disease` (shared across arms, so it reveals nothing).

## Independence (framework §6c)

The pilot is Claude-curated, so `--judge-provider auto` prefers a **different model
family** — OpenAI (`gpt-5`) when `OPENAI_API_KEY` is set — to break the shared-prior
problem. With only an Anthropic key it falls back to `claude-opus-4-8` and prints an
explicit *reduced-independence* note (independence then rests on grounding +
cite-or-abstain, not model diversity). Override with `--judge-provider` / `--judge-model`.

## Modes (no real API call by default)

| mode        | flag        | API?  | what it does                                            |
|-------------|-------------|-------|---------------------------------------------------------|
| dry-run     | *(default)* | none  | discover + blind + resolve legacy paths; print the plan and the judge that *would* run |
| real judge  | `--run`     | yes   | builds a live backend (needs an API key) and judges     |
| offline     | `--stub`    | none  | runs the full orchestration with the deterministic `StubBackend` — for tests/CI, works even when a key is present |

## Usage

```bash
# Plan only (no API):
python scripts/run_blinded_judge.py opus=<dir> sonnet=<dir> \
    --eval-pairs <eval_pairs.yaml> --out-dir experiments/<pilot>/blinded

# Offline orchestration check (no API):
python scripts/run_blinded_judge.py opus=<dir> sonnet=<dir> --stub --out-dir /tmp/bj

# Real blinded pass (cross-family default; needs OPENAI_API_KEY):
python scripts/run_blinded_judge.py <dir> --run --out-dir experiments/<pilot>/blinded
```

Each positional input is a directory (arm label = its basename) or `LABEL=DIR`.

## Legacy / gold comparison (optional, read-only)

Pass `--eval-pairs <file>` (a `pairs:` list of `{id, legacy_path_id}`) and `--kb-dir`
(read-only; default `kb/paths`). The harness matches each curated file to a pair (by
filename stem or the leading token of `graph._id`, or a `graph.legacy_path_id` on the
record), loads the legacy path as the judge's `gold_path`, and the path judge emits
`gold_comparison`. Without `--eval-pairs`, gold comparison is simply skipped. The
harness never writes to `kb/`.

## Calibration caveat

Per framework §7, the judge **proposes; a human disposes** until per-sub-check Cohen's κ
against a blinded ≥2-rater human sample clears threshold. Read these tables as review
prompts and a comparison signal, not as final gates.
