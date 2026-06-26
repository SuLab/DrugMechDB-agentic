"""
DrugMechDB LLM judge layer (semantic quality — Layers 5/6/7).

Operationalizes docs/path_quality_framework.md and the prompt specs in
scripts/quality/prompts/. The judge is qualified by *grounding* (independent
sources + cite-or-abstain), not by intelligence — so this package's core is the
grounding tools (grounding.py) the model must cite, a provider-agnostic agentic
tool-loop (backends.py), and a runner (runner.py) that drives the two judge
prompts. The orchestrator scripts/quality/quality_profile.py merges these with
the deterministic layers (qc.py + structural_quality.py) into one quality profile.
"""
