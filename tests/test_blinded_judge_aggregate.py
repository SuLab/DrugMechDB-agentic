"""Tests for run_blinded_judge.aggregate().

This function produces the headline number of the validation story, and it had
no tests. The property it now has to hold is epistemic rather than mechanical:

    legacy is a COMPARISON POINT, not a gold standard.

The old aggregate scored "agreement with legacy" as `gold_comparison != disagree`.
That rewards reproducing legacy, so an agent path that correctly FIXES a legacy
error scored as a failure — capping measured quality at "matches human" and
hiding exactly the errors the project exists to find. These tests pin the
replacement: divergence is counted, never scored, and every divergence is routed
to a human.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import run_blinded_judge as bj  # noqa: E402


def _result(blind_id, gold=None, has_legacy=True, overall="accept", legacy_id="L1"):
    return {
        "blind_id": blind_id,
        "record": {"drug": "d", "disease": "x"},
        "has_legacy": has_legacy,
        "legacy_path_id": legacy_id,
        "gold_comparison": gold,
        "path_coherence": {"overall": overall},
        "edge_faithfulness": {},
        "n_edges": 3,
        "n_evidence_edges": 3,
    }


def _reveal(*ids, arm="opus"):
    return [{"blind_id": i, "arm": arm} for i in ids]


def _report(results, reveal):
    """A report shaped the way run_blinded_judge actually emits one."""
    return {
        "tool": "run_blinded_judge",
        "generated_at": "2026-09-13T00:00:00Z",
        "n_paths": len(results),
        "config": {"seed": 0, "eval_pairs": None},
        "mode": "stub",
        "judge": {"provider": "stub", "model": None, "note": "STUB"},
        "results": results,
        "reveal_key": [{**r, "legacy_path_id": "L1", "source_file": "f.yaml"} for r in reveal],
        "aggregate": bj.aggregate(results, reveal),
    }


class TestLegacyIsNotGold:
    def test_divergence_is_counted_not_scored_as_failure(self):
        agg = bj.aggregate(
            [_result("B1", "disagree"), _result("B2", "reproduces"),
             _result("B3", "agent_more_complete"), _result("B4", "agent_simpler_but_valid")],
            _reveal("B1", "B2", "B3", "B4"))
        ld = agg["legacy_divergence"]
        assert ld["n_with_legacy"] == 4
        assert ld["n_divergent"] == 1
        assert ld["divergence_rate"] == 0.25

    def test_no_agreement_metric_survives(self):
        """Regression guard: the old framing must not come back. A single
        'agreement' fraction is what made fixing a legacy error look like a miss."""
        agg = bj.aggregate([_result("B1", "disagree")], _reveal("B1"))
        assert "agreement_with_legacy" not in agg
        assert "agreement_with_legacy_by_arm" not in agg

    def test_agent_more_complete_is_not_a_divergence(self):
        """A more complete path is a shape difference the judge already read as
        compatible — not a disagreement about the mechanism."""
        agg = bj.aggregate([_result("B1", "agent_more_complete")], _reveal("B1"))
        assert agg["legacy_divergence"]["n_divergent"] == 0
        assert agg["adjudication_queue"] == []

    def test_divergence_note_states_the_policy(self):
        agg = bj.aggregate([_result("B1", "disagree")], _reveal("B1"))
        note = agg["legacy_divergence"]["note"].lower()
        assert "not error" in note and "gold standard" in note


class TestAdjudicationQueue:
    def test_every_divergence_is_queued_for_a_human(self):
        agg = bj.aggregate(
            [_result("B1", "disagree"), _result("B2", "reproduces"),
             _result("B3", "disagree")],
            _reveal("B1", "B2", "B3"))
        queue = agg["adjudication_queue"]
        assert [q["blind_id"] for q in queue] == ["B1", "B3"]
        assert all(q["verdict"] == "UNADJUDICATED" for q in queue)
        assert all(q["ruling"] is None for q in queue)

    def test_queue_carries_what_a_reviewer_needs(self):
        agg = bj.aggregate([_result("B1", "disagree", legacy_id="DB01_MESH_D1_1")],
                           _reveal("B1"))
        item = agg["adjudication_queue"][0]
        assert item["legacy_path_id"] == "DB01_MESH_D1_1"
        assert item["record"]["drug"] == "d"
        assert item["gold_comparison"] == "disagree"

    def test_overall_accepted_as_dict_or_string(self):
        """The prompt schema says {verdict, summary}; some paths emit a bare
        verdict string, and the verdict tally relies on the string form."""
        as_dict = bj.aggregate(
            [_result("B1", "disagree", overall={"verdict": "revise", "summary": "chain nets +"})],
            _reveal("B1"))
        assert as_dict["adjudication_queue"][0]["judge_summary"] == "chain nets +"

        as_str = bj.aggregate([_result("B2", "disagree", overall="revise")], _reveal("B2"))
        assert as_str["adjudication_queue"][0]["judge_summary"] is None

    def test_paths_without_a_legacy_counterpart_are_not_queued(self):
        agg = bj.aggregate([_result("B1", None, has_legacy=False)], _reveal("B1"))
        assert agg["adjudication_queue"] == []
        assert agg["legacy_divergence"]["n_with_legacy"] == 0
        assert agg["legacy_divergence"]["divergence_rate"] is None


class TestPerArm:
    def test_divergence_split_by_arm(self):
        agg = bj.aggregate(
            [_result("B1", "disagree"), _result("B2", "reproduces"),
             _result("B3", "disagree"), _result("B4", "disagree")],
            _reveal("B1", "B2", arm="opus") + _reveal("B3", "B4", arm="sonnet"))
        by_arm = agg["legacy_divergence_by_arm"]
        assert by_arm["opus"]["n_divergent"] == 1
        assert by_arm["sonnet"]["n_divergent"] == 2
        assert by_arm["sonnet"]["divergence_rate"] == 1.0

    def test_arm_recorded_on_each_queue_item(self):
        agg = bj.aggregate([_result("B1", "disagree")], _reveal("B1", arm="sonnet"))
        assert agg["adjudication_queue"][0]["arm"] == "sonnet"


class TestWorksheetIsNotClobbered:
    def test_existing_queue_file_is_preserved(self, tmp_path, capsys):
        """A re-run must never overwrite rulings a human already made."""
        existing = tmp_path / "adjudication_queue.yaml"
        existing.write_text("queue:\n- blind_id: B1\n  ruling: ai_correct\n")
        results, reveal = [_result("B1", "disagree")], _reveal("B1")
        bj._write_outputs(tmp_path, _report(results, reveal))
        assert "ai_correct" in existing.read_text()
        assert "leaving existing" in capsys.readouterr().out

    def test_worksheet_written_when_absent(self, tmp_path):
        results, reveal = [_result("B1", "disagree")], _reveal("B1")
        bj._write_outputs(tmp_path, _report(results, reveal))
        text = (tmp_path / "adjudication_queue.yaml").read_text()
        assert "ai_correct" in text and "legacy_correct" in text
        assert "not blinded" in text or "necessarily unblinded" in text

    def test_no_worksheet_when_nothing_diverges(self, tmp_path):
        results, reveal = [_result("B1", "reproduces")], _reveal("B1")
        bj._write_outputs(tmp_path, _report(results, reveal))
        assert not (tmp_path / "adjudication_queue.yaml").exists()


class TestRenderingStillWorks:
    def test_markdown_mentions_adjudication_not_agreement(self):
        results, reveal = [_result("B1", "disagree")], _reveal("B1")
        md = bj.render_markdown(_report(results, reveal))
        assert "Divergence from legacy" in md
        assert "Adjudication queue" in md
        assert "Agreement with legacy" not in md
