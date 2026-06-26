# `scripts/quality/judge/` — the semantic judge layer (Layers 5/6/7)

The runnable implementation of the LLM judge described in
`docs/path_quality_framework.md` §3–§7 and `docs/quality_system_design.md` §4. It sits
**above** the syntactic QC gate (Layers 1–4) and the deterministic structural scorer:
those check *well-formedness*; this checks whether the evidence actually *establishes the
edge* and whether the chain is the *accepted mechanism*.

Founding principle (framework §6): **the judge is qualified by grounding, not intelligence.**
It must cite an external referent — the cited source text or an independent oracle (ChEMBL) —
or **abstain** to a human. It never grades from parametric memory, and it re-derives the
`supports` / `evidence_source` labels independently of the curator's self-grade.

## Layout

| File | Role |
|---|---|
| `grounding.py` | The external referents the judge cites: `read_source` (cited PMID text + snippet context via the `pubmed_fetch` wrapper) and `chembl_get_mechanism` (ChEMBL drug→target→action; resolves salt/parent forms). Deterministic, cached (`quality_cache/grounding/`), never raises. |
| `backends.py` | Provider-agnostic agentic **tool-loop**: `AnthropicBackend`, `OpenAIBackend`, `StubBackend` (deterministic; runs the whole pipeline offline with no key). |
| `runner.py` | Loads a prompt's SYSTEM section, drives the loop, robustly parses the JSON verdict, caches verdicts (`quality_cache/verdicts/`). |
| `edge_evidence_judge.py` | Builds the per-edge input the `edge_evidence_judge.md` prompt expects; returns one verdict per edge (the 8-check atomic ladder + re-derived `EvidenceSupportEnum`). |
| `path_coherence_judge.py` | Builds the path-level input for `path_coherence_judge.md`; returns the chain verdict (accepted MoA, net effect, missing/wrong step, primacy, gold comparison). |

The orchestrator that ties everything together is one level up:
`scripts/quality/quality_profile.py`.

## Running it

```bash
# Deterministic layers only (always works, no key):
just quality-profile kb/paths/<file>.yaml --no-llm

# Full profile incl. semantic judges (requires an LLM API key):
export ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY (preferred for independence)
just quality-profile kb/paths/<file>.yaml
just quality-profile-json kb/paths/<file>.yaml      # machine-readable
```

**Independence.** The curator defaults to Claude, so the judge prefers **OpenAI** for
cross-family checking (it breaks the shared-prior problem — framework §6c). Override with
`DMDB_JUDGE_PROVIDER=anthropic|openai` and `DMDB_JUDGE_MODEL=...`. With only an Anthropic key
the judge runs on a non-Opus Claude model and prints a reduced-independence note. With **no**
key, the deterministic profile is still produced and the semantic section is `not_run`.

Install the LLM SDKs for the live path: `pip install -e ".[judge]"`.

## What is NOT done yet: calibration

Construction is complete; **trust is not yet earned.** Per framework §7, the judge's outputs
must be scored against a blinded, ≥2-rater human sample with **per-sub-check Cohen's κ**, and
auto-trusted only on the sub-checks that clear threshold (verbatim/polarity/entity-linking will
clear first; coverage/primacy last). Until then the judge **proposes; a human disposes** — its
verdicts are review prompts, not final gates. The per-check booleans and cited grounding the
prompts emit are the calibration anchors; `quality_cache/verdicts/` preserves the audit trail.

## Testing

`tests/test_quality_judge.py` exercises every seam offline with `StubBackend` (tool-loop,
JSON parsing, edge/path input construction, faithfulness scoring, the full qc+structural+semantic
merge), plus the live Anthropic/OpenAI loops via monkeypatched SDK clients (no key/network) and
network-gated live grounding (`DMDB_NETWORK_TESTS=1`).
