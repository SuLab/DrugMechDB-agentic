"""
Offline, build-only verification for scripts/curate_engine.py + the campaign
AgenticBackend.

The whole engine is exercised end-to-end with a MOCK LLM client (canned tool-use
turns ending in write_path_yaml -> canonicalize_predicates -> run_gate). The load-
bearing guarantees proven here, with NO real Anthropic API call and NO network:

  1. No real Anthropic call — `anthropic.Anthropic` is monkeypatched to blow up; the
     whole suite still passes, so the real constructor is never reached.
  2. The multi-turn loop runs, the REAL gate is invoked, and the output lands in an
     isolated scratch dir — never kb/paths.
  3. Provenance is stamped (on the result and in a sidecar).
  4. Thinking blocks are preserved across turns (run_arm dropped them).
  5. The tool surface is exactly the 8-tool corpus-blind allowlist — no bash, no
     corpus read; read_reference cannot escape the isolated cache dir.
  6. curate_one REFUSES to write inside kb/paths.
  7. A bounded worker pool runs >= 2 items in parallel, each with an isolated cache +
     distinct output; concurrency is proven with a Barrier that would deadlock if the
     pool ran sequentially.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

import curate_engine  # noqa: E402
import campaign_runner  # noqa: E402
from campaign_runner import WorkItem, AgenticBackend, StubBackend, ItemResult  # noqa: E402

KB_PATHS = REPO / "kb" / "paths"

# A path that passes the real gate offline (Layers 1-3 + structural; --no-critic).
# Verified: verdict PASS. (The drug->protein->disease chain is structurally clean;
# scientific truth is the critic's job, which is off in the deterministic gate.)
FIXTURE_YAML = """\
directed: true
multigraph: true
graph:
  _id: DB00945_MESH_D009203_1
  drug: Aspirin
  drug_mesh: MESH:D001241
  drugbank: DB:DB00945
  disease: Myocardial infarction
  disease_mesh: MESH:D009203
nodes:
  - id: MESH:D001241
    name: Aspirin
    label: Drug
  - id: UniProt:P23219
    name: Prostaglandin G/H synthase 1
    label: Protein
  - id: MESH:D009203
    name: Myocardial infarction
    label: Disease
links:
  - key: decreases activity of
    source: MESH:D001241
    target: UniProt:P23219
  - key: causes
    source: UniProt:P23219
    target: MESH:D009203
"""


# ── a mock Anthropic Messages client (canned tool-use turns; zero network) ─────

class _Block:
    def __init__(self, type, **attrs):
        self.type = type
        for k, v in attrs.items():
            setattr(self, k, v)


class _Usage:
    def __init__(self, **kw):
        self.input_tokens = kw.get("input_tokens", 100)
        self.output_tokens = kw.get("output_tokens", 50)
        self.cache_read_input_tokens = kw.get("cache_read_input_tokens", 0)
        self.cache_creation_input_tokens = kw.get("cache_creation_input_tokens", 0)


class _Resp:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _Usage()


class _MockMessages:
    def __init__(self, client):
        self._client = client

    def create(self, **kwargs):
        c = self._client
        c.calls.append(kwargs)
        if c.on_first_create is not None and not c._tripped:
            c._tripped = True
            c.on_first_create()
        if c._turns:
            content, stop = c._turns.pop(0)
            return _Resp(content, stop)
        return _Resp([_Block("text", text="done")], "end_turn")


class MockClient:
    """Drop-in for anthropic.Anthropic — plays back scripted turns; never touches
    the network. `on_first_create` fires once (used to prove parallelism)."""
    def __init__(self, turns, on_first_create=None):
        self._turns = list(turns)
        self.calls = []
        self.on_first_create = on_first_create
        self._tripped = False
        self.messages = _MockMessages(self)


def _curate_script(yaml_content=FIXTURE_YAML, with_thinking=True):
    """The canned /curate transcript: (think) -> write -> canonicalize -> gate -> report."""
    first_blocks = []
    if with_thinking:
        first_blocks.append(_Block("thinking", thinking="Aspirin inhibits COX-1.",
                                   signature="sig-abc123"))
    first_blocks += [
        _Block("text", text="Drafting the path."),
        _Block("tool_use", id="tu_write", name="write_path_yaml",
               input={"yaml_content": yaml_content}),
    ]
    return [
        (first_blocks, "tool_use"),
        ([_Block("tool_use", id="tu_canon", name="canonicalize_predicates", input={})], "tool_use"),
        ([_Block("tool_use", id="tu_gate", name="run_gate", input={})], "tool_use"),
        ([_Block("text", text="Done — gate PASS. Cited nothing (mock).")], "end_turn"),
    ]


@pytest.fixture
def no_real_anthropic(monkeypatch):
    """Make any real Anthropic construction a hard failure — so the suite proves,
    by passing, that no real client is ever built."""
    import anthropic

    def _boom(*a, **k):
        raise AssertionError("a real anthropic.Anthropic() was constructed during a test")

    monkeypatch.setattr(anthropic, "Anthropic", _boom)


# ── 1+2+3+4: end-to-end offline curation with a mock client ────────────────────

def test_end_to_end_offline_curation(tmp_path, no_real_anthropic):
    out_path = tmp_path / "paths" / "DB00945_MESH_D009203_1.yaml"
    cache_dir = tmp_path / "cache" / "DB00945_MESH_D009203_1"
    item = WorkItem(id="DB00945_MESH_D009203_1", drug="Aspirin",
                    disease="Myocardial infarction", disease_mesh="MESH:D009203",
                    drugbank="DB:DB00945", drug_mesh="MESH:D001241")
    client = MockClient(_curate_script())

    res = curate_engine.curate_one(item, model="claude-opus-4-8",
                                   cache_dir=cache_dir, out_path=out_path, client=client)

    # loop ran the full write -> canonicalize -> gate -> report transcript
    assert res.iters == 4
    assert res.stopped == "end_turn"
    assert res.tool_call_counts == {"write_path_yaml": 1,
                                    "canonicalize_predicates": 1, "run_gate": 1}
    # the REAL gate was invoked and returned union feedback
    assert res.gate_verdict == "PASS"
    assert res.gate_passed is True
    assert res.gate_feedback and res.gate_feedback["record_id"] == "DB00945_MESH_D009203_1"
    assert res.ok is True

    # output landed in the isolated scratch dir — NOT kb/paths
    assert res.output_written and out_path.exists()
    assert KB_PATHS.resolve() not in out_path.resolve().parents
    assert yaml.safe_load(out_path.read_text())["graph"]["_id"] == "DB00945_MESH_D009203_1"

    # provenance stamped on the result AND written to a sidecar in the scratch dir
    assert res.provenance and res.provenance["model"] == "claude-opus-4-8"
    assert res.provenance.get("prompt_version") and "curated_at" in res.provenance
    sidecar = out_path.with_suffix(out_path.suffix + ".provenance.json")
    assert sidecar.exists()

    # prompt caching: a cache_control breakpoint sits on the system block
    assert client.calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}

    # thinking blocks preserved across turns (the 2nd request replays the assistant
    # turn from turn 1, which must still carry the thinking block + signature)
    replayed = client.calls[1]["messages"]
    asst = next(m for m in replayed if m["role"] == "assistant")
    tk = [b for b in asst["content"] if b.get("type") == "thinking"]
    assert tk and tk[0]["thinking"] == "Aspirin inhibits COX-1." and tk[0]["signature"] == "sig-abc123"


# ── 5: the corpus-blind 8-tool allowlist ──────────────────────────────────────

def test_tool_allowlist_is_exactly_eight_and_corpus_blind(tmp_path):
    tool_defs, registry, _state = curate_engine.build_tools(
        tmp_path / "cache", tmp_path / "out.yaml")
    names = {t["name"] for t in tool_defs}
    assert names == {
        "evidence_search", "evidence_fetch", "evidence_probe", "read_reference",
        "write_path_yaml", "read_path_yaml", "canonicalize_predicates", "run_gate",
    }
    assert len(tool_defs) == 8 and set(registry) == names
    # No shell / general file read / corpus access exists in the surface, by construction.
    lowered = " ".join(names).lower()
    for banned in ("bash", "shell", "exec", "glob", "grep", "list_dir", "read_file", "kb"):
        assert banned not in lowered


def test_read_reference_cannot_escape_isolated_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    _defs, registry, _state = curate_engine.build_tools(cache_dir, tmp_path / "out.yaml")
    read_reference = registry["read_reference"]

    # A reference not fetched into THIS cache is unreadable.
    assert "not in cache" in read_reference({"reference": "PMID:35569550"})

    # Seed the isolated cache the way the fetch tool would, then it reads back.
    from evidence_sources import common
    seeded = cache_dir / common.cache_filename("PMID:35569550")
    seeded.write_text("---\nreference_id: PMID:35569550\n---\n\n## Content\n\nverbatim body.")
    assert "verbatim body." in read_reference({"reference": "PMID:35569550"})

    # Path-traversal refs collapse to a bare filename inside the cache dir — they cannot
    # reach the corpus or anywhere else; the read simply misses in the isolated cache.
    for evil in ("../../kb/paths/DB00945_MESH_D009203_1", "url:../../../etc/passwd"):
        out = read_reference({"reference": evil})
        assert out.startswith("ERROR")
        assert "directed: true" not in out  # never returns a real corpus record


# ── 6: the engine refuses to write inside the corpus ───────────────────────────

def test_refuses_to_write_inside_kb_paths(tmp_path):
    item = WorkItem(id="X_Y_1", drug="d", disease="e")
    client = MockClient(_curate_script())
    with pytest.raises(ValueError, match="corpus"):
        curate_engine.curate_one(item, cache_dir=tmp_path / "cache",
                                 out_path=KB_PATHS / "X_Y_1.yaml", client=client)
    with pytest.raises(ValueError, match="corpus"):
        curate_engine.curate_one(item, cache_dir=KB_PATHS / "cache",
                                 out_path=tmp_path / "out.yaml", client=client)


# ── 7: bounded worker pool, isolated, provably parallel ────────────────────────

def test_worker_pool_parallel_isolation(tmp_path, no_real_anthropic):
    items = [
        WorkItem(id="A_A_1", drug="DrugA", disease="DisA", disease_mesh="MESH:D000001"),
        WorkItem(id="B_B_1", drug="DrugB", disease="DisB", disease_mesh="MESH:D000002"),
    ]
    # A Barrier(2) tripped on each worker's first model call: if the pool ran the two
    # items sequentially, the first worker would block forever waiting for the second,
    # so this rendezvous only completes under genuine concurrency.
    barrier = threading.Barrier(2, timeout=15)

    def factory():
        return MockClient(_curate_script(), on_first_create=barrier.wait)

    backend = AgenticBackend(out_dir=tmp_path, workers=2, client_factory=factory)
    results = backend.run(items)

    assert set(results) == {"A_A_1", "B_B_1"}
    for wid in ("A_A_1", "B_B_1"):
        assert results[wid].ok, results[wid].error
        out_file = tmp_path / "paths" / f"{wid}.yaml"
        assert out_file.exists()
        assert (tmp_path / "cache" / wid).is_dir()          # per-worker isolated cache
        assert (out_file.with_suffix(".yaml.provenance.json")).exists()
    # distinct outputs + caches — no collision between workers
    assert (tmp_path / "paths" / "A_A_1.yaml").read_text()  # both written
    assert KB_PATHS.resolve() not in (tmp_path / "paths").resolve().parents


# ── the stub backend stays intact; CLI default is a dry run ────────────────────

def test_stub_backend_intact_and_backends_present():
    stub = StubBackend(fail_ids={"z"})
    out = stub.run([WorkItem(id="a"), WorkItem(id="z")])
    assert out["a"].ok and not out["z"].ok
    assert AgenticBackend.name == "agentic"


def test_module_import_has_no_side_effects(no_real_anthropic):
    # Importing the engine (already imported at top) must not construct a client or curate.
    import importlib
    importlib.reload(curate_engine)   # would raise via no_real_anthropic if it built a client
    assert curate_engine.main([]) == 0  # dry-run CLI makes no API call
