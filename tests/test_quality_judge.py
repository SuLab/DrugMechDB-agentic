"""
Tests for the semantic judge layer (scripts/quality/judge/) and the quality_profile
orchestrator. The deterministic seams — tool-loop execution, JSON verdict parsing,
edge/path input construction, faithfulness scoring, and the qc+structural+semantic
merge — are exercised end-to-end with a deterministic StubBackend, so the full
pipeline is verified WITHOUT any API key. Grounding tools are tested live but
network-gated (DMDB_NETWORK_TESTS=1).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts" / "quality"))

from judge.backends import StubBackend, Tool  # noqa: E402
from judge.runner import extract_json, load_system_prompt, run_judge  # noqa: E402
from judge import edge_evidence_judge as eej  # noqa: E402
import quality_profile as qp  # noqa: E402

EDGE_PROMPT = REPO / "scripts" / "quality" / "prompts" / "edge_evidence_judge.md"
PATH_PROMPT = REPO / "scripts" / "quality" / "prompts" / "path_coherence_judge.md"
NETWORK = os.environ.get("DMDB_NETWORK_TESTS") == "1"
net = pytest.mark.skipif(not NETWORK, reason="set DMDB_NETWORK_TESTS=1 for live grounding tests")


# ── JSON extraction ─────────────────────────────────────────────────────────

def test_extract_json_fenced_and_prose():
    assert extract_json('prefix ```json\n{"a": 1}\n``` suffix') == {"a": 1}
    assert extract_json('here you go: {"x": [1,2], "y": "}"}\nthanks') == {"x": [1, 2], "y": "}"}
    assert extract_json("[1, 2, 3]") == [1, 2, 3]
    assert "_parse_error" in extract_json("no json here")


def test_load_system_prompt_strips_heading():
    sp = load_system_prompt(EDGE_PROMPT)
    assert "independent evidence verifier" in sp
    assert "## SYSTEM PROMPT" not in sp


# ── tool-loop execution (StubBackend drives the real loop + executor) ─────────

def test_stub_loop_executes_tools_then_finalizes():
    seen = {}
    mock = Tool(
        name="read_source",
        description="mock",
        input_schema={"type": "object", "properties": {"reference": {"type": "string"}}},
        fn=lambda a: (seen.__setitem__("called_with", a), "MOCK SOURCE TEXT")[1],
    )
    script = [
        {"call": [{"name": "read_source", "input": {"reference": "PMID:1"}}]},
        {"final": '{"edge_supported": true, "verdicts": []}'},
    ]
    out = run_judge(EDGE_PROMPT, {"edge": {}}, [mock], StubBackend(script), use_cache=False)
    assert seen["called_with"] == {"reference": "PMID:1"}          # tool actually executed
    assert out["tool_calls"][0]["name"] == "read_source"
    assert out["verdict"] == {"edge_supported": True, "verdicts": []}
    assert out["stopped"] == "final"


def test_unavailable_tool_does_not_crash_loop():
    script = [{"call": [{"name": "nonexistent", "input": {}}]}, {"final": "{}"}]
    out = run_judge(EDGE_PROMPT, {}, [], StubBackend(script), use_cache=False)
    assert "not available" in out["tool_calls"][0]["result_preview"]
    assert out["verdict"] == {}


# ── edge-evidence judge: the P06 endoxifen case re-derives PARTIAL ────────────

def _p06_like_doc() -> dict:
    return {
        "directed": True, "multigraph": True,
        "graph": {"_id": "X_1", "drug": "Tamoxifen", "disease": "Breast Neoplasms"},
        "nodes": [
            {"id": "MESH:D013629", "name": "Tamoxifen", "label": "Drug"},
            {"id": "UniProt:P03372", "name": "Estrogen receptor", "label": "Protein"},
        ],
        "links": [{
            "key": "decreases activity of", "source": "MESH:D013629", "target": "UniProt:P03372",
            "evidence": [{
                "reference": "PMID:42210419",
                "snippet": "Endoxifen is a potent antiestrogen that binds and blocks estrogen receptor alpha",
                "supports": "SUPPORT", "evidence_source": "IN_VITRO",
            }],
        }],
    }


def _edge_responder(user: str):
    """A stub judge: returns PARTIAL when the snippet's subject (endoxifen) differs
    from the edge subject (tamoxifen); SUPPORT otherwise."""
    inp = json.loads(user)
    ev = inp["evidence"][0]
    subj = inp["edge"]["subject"]["name"] or ""
    snip = ev["snippet"].lower()
    if subj.lower() == "tamoxifen" and "endoxifen" in snip:
        verdict = {
            "edge_id": "tamoxifen|decreases activity of|ER",
            "verdicts": [{
                "reference": ev["reference"],
                "checks": {"subject_grounding": {"result": "fail", "basis": "snippet subject is endoxifen, not tamoxifen"}},
                "rederived_supports": "PARTIAL",
                "agrees_with_curator": False,
                "note": "snippet about the metabolite endoxifen",
            }],
            "edge_supported": True,
            "edge_basis": "ChEMBL CHEMBL786 tamoxifen->ESR1 modulator",
        }
    else:
        verdict = {"verdicts": [{"reference": ev["reference"], "rederived_supports": "SUPPORT",
                                 "agrees_with_curator": True}], "edge_supported": True}
    return [{"final": json.dumps(verdict)}]


def test_edge_judge_rederives_partial_for_metabolite_snippet():
    doc = _p06_like_doc()
    verdicts = eej.judge_edges(doc, StubBackend(_edge_responder), tools=[], use_cache=False)
    assert len(verdicts) == 1
    v = verdicts[0]["verdict"]
    assert v["verdicts"][0]["rederived_supports"] == "PARTIAL"
    assert v["verdicts"][0]["agrees_with_curator"] is False


def test_build_edge_inputs_shape():
    inputs = eej.build_edge_inputs(_p06_like_doc())
    e = inputs[0]
    assert e["edge"]["subject"]["name"] == "Tamoxifen"
    assert e["edge"]["object"]["label"] == "Protein"
    assert e["evidence"][0]["reference"] == "PMID:42210419"
    assert "Tamoxifen --decreases activity of--> Estrogen receptor" in e["path_context"]


# ── orchestrator end-to-end with a stub judge (no key, no network) ────────────

def _responder(user: str):
    inp = json.loads(user)
    if "structural_report" in inp:   # path-coherence judge
        return [{"final": json.dumps({
            "mechanism_is_accepted": {"verdict": "yes", "basis": "ChEMBL"},
            "net_effect_correct": {"verdict": "yes"},
            "overall": {"verdict": "accept", "summary": "edges supported; chain coherent"},
            "routed_to_human": False,
        })}]
    # edge judge
    ev = inp["evidence"][0]
    return [{"final": json.dumps({
        "verdicts": [{"reference": ev["reference"], "rederived_supports": "SUPPORT",
                      "agrees_with_curator": True, "checks": {}}],
        "edge_supported": True,
    })}]


def test_quality_profile_end_to_end_stub():
    fixture = REPO / "tests" / "fixtures" / "sample_ai_curated.yaml"
    if not fixture.exists() or not (REPO / "references_cache" / "PMID_99999999.md").exists():
        pytest.skip("ai_curated fixture or sentinel cache not present")
    prof = qp.quality_profile(str(fixture), run_llm=True, backend=StubBackend(_responder), use_cache=False)
    # syntactic gates present
    assert set(prof["hard_gates"]) == {
        "schema", "ontology", "predicate_enum", "verbatim_evidence", "connectivity", "net_polarity_negative"}
    # semantic layer ran and merged
    assert prof["semantic"]["status"] == "run"
    ef = prof["semantic"]["edge_faithfulness"]
    assert ef["status"] == "run" and ef["n_evidence"] >= 1
    assert ef["support_fraction"] == 1.0
    assert prof["semantic"]["path_coherence"]["overall"]["verdict"] == "accept"
    assert prof["overall"] in ("accept", "review", "reject", "revise")


def test_edge_faithfulness_flags_partial():
    edge_verdicts = [{
        "edge": {"subject": {"name": "Tamoxifen"}, "predicate": "decreases activity of", "object": {"name": "ER"}},
        "verdict": {"verdicts": [{"reference": "PMID:1", "rederived_supports": "PARTIAL",
                                  "agrees_with_curator": False, "checks": {}}]},
    }]
    ef = qp.edge_faithfulness(edge_verdicts)
    assert ef["n_evidence"] == 1 and ef["n_support"] == 0
    assert ef["flagged_edges"][0]["rederived_supports"] == "PARTIAL"


# ── grounding tools (live, network-gated) ─────────────────────────────────────

@net
def test_grounding_chembl_tamoxifen():
    from judge import grounding as g
    out = g.chembl_get_mechanism("tamoxifen")
    assert "Estrogen receptor" in out and ("MODULATOR" in out or "modulator" in out.lower())


@net
def test_grounding_read_source():
    from judge import grounding as g
    out = g.read_source("PMID:41879452", snippet="Allopurinol and its active metabolite, oxypurinol")
    assert "verbatim-present" in out and "True" in out


# ── live backends: tool-loop exercised against a monkeypatched SDK (no key) ────

class _NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)
    def model_dump(self):
        return dict(self.__dict__)


def _mock_tool():
    hits = {"n": 0}
    return hits, Tool(
        name="read_source", description="m",
        input_schema={"type": "object", "properties": {"reference": {"type": "string"}}},
        fn=lambda a: (hits.__setitem__("n", hits["n"] + 1), "GROUNDING TEXT")[1],
    )


def test_anthropic_backend_tool_loop_monkeypatched(monkeypatch):
    anthropic = pytest.importorskip("anthropic", reason="install the 'judge' extra to test the live backend")
    from judge.backends import AnthropicBackend

    class FakeMessages:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                return _NS(stop_reason="tool_use",
                          content=[_NS(type="text", text="checking"),
                                   _NS(type="tool_use", id="t1", name="read_source", input={"reference": "PMID:1"})],
                          usage=_NS(input_tokens=10, output_tokens=5))
            return _NS(stop_reason="end_turn",
                       content=[_NS(type="text", text='{"edge_supported": true}')],
                       usage=_NS(input_tokens=3, output_tokens=4))

    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: _NS(messages=FakeMessages()))
    hits, tool = _mock_tool()
    res = AnthropicBackend("fake-claude").run("sys", "user", [tool], max_iters=4)
    assert hits["n"] == 1                       # the tool actually executed mid-loop
    assert res.final_text == '{"edge_supported": true}'
    assert res.iters == 2 and res.stopped == "final"
    assert res.usage["input_tokens"] == 13      # summed across turns


def test_openai_backend_tool_loop_monkeypatched(monkeypatch):
    openai = pytest.importorskip("openai", reason="install the 'judge' extra to test the live backend")
    from judge.backends import OpenAIBackend

    class FakeCompletions:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                tc = _NS(id="c1", type="function",
                         function=_NS(name="read_source", arguments='{"reference": "PMID:1"}'))
                return _NS(choices=[_NS(message=_NS(content=None, tool_calls=[tc]))])
            return _NS(choices=[_NS(message=_NS(content='{"edge_supported": true}', tool_calls=None))])

    fake_client = _NS(chat=_NS(completions=FakeCompletions()))
    monkeypatch.setattr(openai, "OpenAI", lambda *a, **k: fake_client)
    hits, tool = _mock_tool()
    res = OpenAIBackend("fake-gpt").run("sys", "user", [tool], max_iters=4)
    assert hits["n"] == 1
    assert res.final_text == '{"edge_supported": true}'
    assert res.iters == 2 and res.stopped == "final"
