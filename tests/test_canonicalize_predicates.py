"""
Coverage for scripts/canonicalize_predicates.py — the deterministic predicate
surface-form normalizer that runs BEFORE the Layer-3 exact-match gate.

Tests the two pure functions that carry the behaviour (normalize + canonicalize)
plus the enum/alias loaders. No file scanning and no --write: the CLI writes a
summary into docs/, so we exercise the logic directly instead. Load-bearing
properties:

  * each step of the documented pipeline (strip, whitespace-collapse,
    biolink: prefix, underscore->space, lowercase) actually happens;
  * a drifted surface form lands on a real BiolinkPredicate enum member;
  * the alias map is applied on top of normalization;
  * the transform is idempotent (running it twice changes nothing).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import canonicalize_predicates as cp  # noqa: E402

ENUM = cp.load_enum()


# ─── normalize() pipeline ────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("decreases activity of", "decreases activity of"),   # already canonical
    ("  decreases activity of  ", "decreases activity of"),  # strip
    ("decreases   activity\tof", "decreases activity of"),   # collapse whitespace
    ("Decreases Activity Of", "decreases activity of"),      # lowercase
    ("biolink:decreases_activity_of", "decreases activity of"),  # prefix + underscores
    ("BIOLINK:Decreases_Activity_Of", "decreases activity of"),  # all of the above
    ("increases_abundance_of", "increases abundance of"),
])
def test_normalize_pipeline(raw, expected):
    assert cp.normalize(raw) == expected


def test_normalize_handles_none():
    assert cp.normalize(None) == ""


def test_normalize_is_idempotent():
    for raw in ("biolink:Decreases_Activity_Of", "  Positively   Regulates ", "CAUSES"):
        once = cp.normalize(raw)
        assert cp.normalize(once) == once


# ─── the surface-form normalizer maps drift onto real enum members ───────────

@pytest.mark.parametrize("raw", [
    "biolink:decreases_activity_of",
    "Decreases  Activity Of",
    "  CAUSES  ",
    "positively_regulates",
    "increases_abundance_of",
])
def test_drifted_forms_canonicalize_into_the_enum(raw):
    canon = cp.canonicalize(raw, aliases={})   # no alias needed; pure normalization
    assert canon in ENUM, f"{raw!r} normalized to {canon!r}, not a BiolinkPredicate"


def test_canonicalize_applies_alias_on_top_of_normalization():
    # aliases key against the NORMALIZED form; a drifted input still hits the alias.
    aliases = {"associated with": "correlated with"}
    assert cp.canonicalize("Associated  With", aliases) == "correlated with"
    assert cp.canonicalize("biolink:associated_with", aliases) == "correlated with"


def test_canonicalize_leaves_canonical_member_unchanged():
    for member in ("decreases activity of", "causes", "part of"):
        assert cp.canonicalize(member, aliases={}) == member


def test_unmapped_drift_stays_out_of_enum():
    """A genuinely unknown predicate must NOT be silently coerced into the enum —
    it should normalize to something the Layer-3 gate will still reject."""
    canon = cp.canonicalize("modulates somehow", aliases={})
    assert canon == "modulates somehow"
    assert canon not in ENUM


# ─── loaders ─────────────────────────────────────────────────────────────────

def test_load_enum_covers_both_biolink_eras():
    """The enum spans eras: current Biolink plus the legacy vocabulary kb/paths uses.

    Its size is not asserted — it grows when we adopt a predicate from a new Biolink
    release. The invariant is that every enum value has a status entry and vice versa,
    since Layer 3 reads the two together.
    """
    import yaml
    status = yaml.safe_load(
        (REPO / "src" / "drugmechdb" / "schema" / "biolink_predicate_status.yaml").read_text()
    )["predicates"]
    assert set(status) == ENUM
    assert "decreases activity of" in ENUM          # legacy-only, still accepted
    assert "affects" in ENUM                        # current Biolink


def test_every_replacement_points_at_a_current_predicate():
    """A `replacement:` that isn't itself a current enum member would migrate a record
    straight into a Layer 3 failure — the mapping has to be closed over the enum."""
    import yaml
    status = yaml.safe_load(
        (REPO / "src" / "drugmechdb" / "schema" / "biolink_predicate_status.yaml").read_text()
    )["predicates"]
    for pred, entry in status.items():
        replacement = entry.get("replacement") or {}
        target = replacement.get("key")
        if not target:
            continue
        assert target in ENUM, f"{pred!r} maps to {target!r}, which is not in the enum"
        assert status[target]["status"] == "current", (
            f"{pred!r} maps to {target!r}, which is not a current predicate")


def test_load_aliases_returns_a_mapping():
    aliases = cp.load_aliases()
    assert isinstance(aliases, dict)   # currently empty; must stay a dict
