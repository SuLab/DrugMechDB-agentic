# DrugMechDB justfile — Phase 2 QC entrypoints.
#
# All targets shell out to scripts/qc.py (the layer orchestrator) using the
# Python 3.10 virtualenv at .venv-py310/. To bootstrap:
#
#     /opt/homebrew/Cellar/python@3.10/3.10.4/.../python3.10 -m venv .venv-py310
#     .venv-py310/bin/pip install -e ".[dev]"
#
# Then `just qc` runs the full pipeline. Pass arbitrary args after `--` to
# qc, e.g. `just qc -- kb/paths/DB00002_MESH_D003110_1.yaml --profile ai_curated`.

PY := ".venv-py310/bin/python"

# default target
default: qc

# Run the full QC pipeline with profile auto-detection (default).
qc *ARGS:
    {{PY}} scripts/qc.py {{ARGS}}

# Force the legacy profile (Layers 1, 2, 3; evidence not required).
qc-legacy *ARGS:
    {{PY}} scripts/qc.py --profile legacy {{ARGS}}

# Force the ai_curated profile (Layers 1, 2, 3, 4; evidence required).
qc-ai *ARGS:
    {{PY}} scripts/qc.py --profile ai_curated {{ARGS}}

# Run a single layer (Layer N) across all files or given args.
qc-layer N *ARGS:
    {{PY}} scripts/qc.py --layer {{N}} {{ARGS}}

# Machine-readable JSON output.
qc-json *ARGS:
    {{PY}} scripts/qc.py --json {{ARGS}}

# Post-QC structural quality analysis (deterministic, no LLM). Reports a quality
# profile + flags; it is a scorer, NOT a pass/fail gate. Run after `just qc` is green.
quality *ARGS:
    {{PY}} scripts/quality/structural_quality.py {{ARGS}}

# Machine-readable per-file structural quality JSON.
quality-json *ARGS:
    {{PY}} scripts/quality/structural_quality.py --json {{ARGS}}

# Full quality profile: QC gate + structural + (if a judge API key is set) the
# semantic LLM judges, merged into one profile per record. Deterministic layers
# always run; semantic layers are marked "not run" without a key. See
# scripts/quality/judge/README.md. Use --no-llm to force deterministic-only.
quality-profile *ARGS:
    {{PY}} scripts/quality/quality_profile.py {{ARGS}}

# Machine-readable quality profile JSON.
quality-profile-json *ARGS:
    {{PY}} scripts/quality/quality_profile.py --json {{ARGS}}

# Phase-1 / 1.5 maintenance helpers (one-shot data cleanups).
normalize:
    {{PY}} scripts/phase1_normalize_paths.py --dry-run

normalize-write:
    {{PY}} scripts/phase1_normalize_paths.py

canonicalize:
    {{PY}} scripts/canonicalize_predicates.py

canonicalize-write:
    {{PY}} scripts/canonicalize_predicates.py --write

rebuild-index:
    {{PY}} scripts/rebuild_index.py

# Pytest suite (tests/).
test *ARGS:
    {{PY}} -m pytest {{ARGS}}

# Show what got installed and which Python is in use.
env-info:
    @echo "Python:" $({{PY}} --version)
    @echo "Venv:" $(dirname $(dirname {{PY}}))
    @{{PY}} -c "import linkml, linkml_runtime, linkml_term_validator, linkml_reference_validator; \
        print(f'linkml={linkml.__version__}'); \
        print(f'linkml-runtime={linkml_runtime.__version__}'); \
        print(f'linkml-term-validator={linkml_term_validator.__version__ if hasattr(linkml_term_validator, \"__version__\") else \"?\"}'); \
        print(f'linkml-reference-validator={linkml_reference_validator.__version__ if hasattr(linkml_reference_validator, \"__version__\") else \"?\"}')"

# ── Term existence (ADVISORY — reports, never gates) ─────────────────────────
# Layer 2 checks that a CURIE's prefix matches its Biolink type; it never asks
# whether the identifier exists. These do. Results are cached under cache/terms/
# (committed), so `terms-offline` reproduces an audit with no network.

# Full corpus audit -> docs/term_existence_audit.{json,md}
terms *ARGS:
    {{PY}} scripts/audit_term_existence.py --json docs/term_existence_audit.json \
        --markdown docs/term_existence_audit.md {{ARGS}}

# Same, but answer only from the committed cache (deterministic, no network).
terms-offline *ARGS:
    {{PY}} scripts/audit_term_existence.py --offline {{ARGS}}

# One authority at a time (the validators named in conf/oak_config.yaml).
terms-mesh *ARGS:
    {{PY}} scripts/validate_mesh.py {{ARGS}}

terms-uniprot *ARGS:
    {{PY}} scripts/validate_uniprot.py {{ARGS}}

terms-reactome *ARGS:
    {{PY}} scripts/validate_reactome.py {{ARGS}}
