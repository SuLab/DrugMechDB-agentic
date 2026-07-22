"""
Bulk re-curation campaign framework — a build-only scaffold that NEVER auto-runs curation.

This is the framework for re-curating the whole corpus (every existing (drug, disease)
record gets a fresh AI-curated path). It does three jobs and nothing else:

  1. Enumerate the work list — every record, from kb/paths/_index.yaml.
  2. Track per-record status in a resumable, idempotent status file so an interrupted
     campaign resumes without redoing finished records.
  3. Dispatch work through a pluggable Backend and stamp provenance on each result.

Backends:
  - StubBackend    — deterministic, no API calls. Lets the whole framework (enumerate,
                     resume, status, provenance) be exercised offline — no spend, no real
                     curation — which is how it is tested.
  - AgenticBackend — the LIVE multi-turn curation backend: dispatches
                     scripts/curate_engine.curate_one per WorkItem over a bounded worker
                     pool, each worker fully isolated (its own DMDB_CACHE_DIR + output
                     path). This is what actually runs the /curate loop at corpus scale.

Curation is inherently a MULTI-TURN loop (search -> fetch -> draft -> gate -> iterate), run as
a continuous process by AgenticBackend. (The Anthropic Batches API runs one model turn per
request and cannot execute a multi-turn tool loop, so it is not used for curation.)

**Safety:** this module never curates on import or by default. The CLI defaults to a dry-run
plan; `--stub` exercises the framework offline. A real run is an explicit, deliberate call —
`CampaignRunner.run(AgenticBackend(...))` — never the default.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import yaml

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "kb" / "paths" / "_index.yaml"
STATUS_FILE = REPO / "_recuration_status.yaml"   # generated, gitignore-able; resumable state (not in kb/paths — never a curation record)
PROMPT_FILES = ["AGENTS.md", "CurationGuide.md"]                  # provenance: what guided curation


# ── work list ─────────────────────────────────────────────────────────────────

@dataclass
class WorkItem:
    id: str
    drug: str | None = None
    disease: str | None = None
    drug_mesh: str | None = None
    disease_mesh: str | None = None
    drugbank: str | None = None


def enumerate_work() -> list[WorkItem]:
    """Every record in the corpus, from the generated index. No prioritization —
    the whole corpus is in scope, in deterministic _id order."""
    doc = yaml.safe_load(INDEX.read_text(encoding="utf-8"))
    entries = doc.values() if isinstance(doc, dict) else doc
    items = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        items.append(WorkItem(
            id=e.get("id") or e.get("_id") or (e.get("file", "").removesuffix(".yaml")),
            drug=e.get("drug"), disease=e.get("disease"),
            drug_mesh=e.get("drug_mesh"), disease_mesh=e.get("disease_mesh"),
            drugbank=e.get("drugbank"),
        ))
    items.sort(key=lambda w: w.id or "")
    return items


# ── provenance ──────────────────────────────────────────────────────────────

def prompt_version() -> str:
    """A stable fingerprint of the curation guidance (AGENTS.md + CurationGuide.md),
    so every curated record records exactly which rules produced it."""
    h = hashlib.sha256()
    for name in PROMPT_FILES:
        p = REPO / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


def git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


def make_provenance(model: str, run_id: str) -> dict:
    return {
        "model": model,
        "prompt_version": prompt_version(),
        "git_sha": git_sha(),
        "run_id": run_id,
        "curated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


# ── resumable status store ────────────────────────────────────────────────────

@dataclass
class StatusStore:
    path: Path = STATUS_FILE
    records: dict = field(default_factory=dict)   # id -> {state, provenance, error}

    STATES = ("pending", "submitted", "done", "failed")

    @classmethod
    def load(cls, path: Path = STATUS_FILE) -> "StatusStore":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        return cls(path=path, records=(data or {}).get("records", {}))

    def save(self) -> None:
        self.path.write_text(
            yaml.safe_dump({"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                            "records": self.records}, sort_keys=False, allow_unicode=True),
            encoding="utf-8")

    def state(self, item_id: str) -> str:
        return self.records.get(item_id, {}).get("state", "pending")

    def pending(self, items: list[WorkItem]) -> list[WorkItem]:
        """Resumability + idempotency: only items not already done."""
        return [w for w in items if self.state(w.id) != "done"]

    def mark(self, item_id: str, state: str, **extra) -> None:
        assert state in self.STATES, state
        rec = self.records.setdefault(item_id, {})
        rec["state"] = state
        rec.update({k: v for k, v in extra.items() if v is not None})

    def counts(self) -> dict:
        c = {s: 0 for s in self.STATES}
        for rec in self.records.values():
            c[rec.get("state", "pending")] = c.get(rec.get("state", "pending"), 0) + 1
        return c


# ── backends ──────────────────────────────────────────────────────────────────

@dataclass
class ItemResult:
    item_id: str
    ok: bool
    error: str | None = None


class Backend(Protocol):
    name: str
    def run(self, items: list[WorkItem],
            build_request: Callable[[WorkItem], object] | None,
            parse_result: Callable[[str, object], ItemResult] | None) -> dict[str, ItemResult]: ...


class StubBackend:
    """Offline, deterministic — fabricates a result per item so the orchestration
    (enumerate, resume, status, provenance) is testable with no API and no curation."""
    name = "stub"

    def __init__(self, fail_ids: set[str] | None = None):
        self.fail_ids = fail_ids or set()

    def run(self, items, build_request=None, parse_result=None) -> dict[str, ItemResult]:
        out = {}
        for w in items:
            ok = w.id not in self.fail_ids
            out[w.id] = ItemResult(w.id, ok, None if ok else "stub-forced-failure")
        return out


class AgenticBackend:
    """LIVE multi-turn curation via scripts/curate_engine.curate_one, one call per
    WorkItem, dispatched over a bounded worker pool. This is what makes a whole-corpus
    re-curation feasible instead of sequential-for-days.

    Isolation (per worker, no shared mutable state):
      * distinct output path   <out_dir>/paths/<id>.yaml           (never kb/paths —
        curate_engine asserts this)
      * distinct cache dir      <out_dir>/cache/<id>/  exported as DMDB_CACHE_DIR to that
        worker's tool subprocesses, so caches never collide
      * a fresh message history

    Parallelism is a ThreadPoolExecutor (tool calls are subprocess/IO-bound, so threads
    give real concurrency); `workers` is bounded with a safe default.

    Clients: pass `client_factory` to give each worker its own client (used by the offline
    tests to inject a mock per worker); else one real `anthropic.Anthropic()` is built once
    and shared across workers (thread-safe). Constructing the real client is deferred until
    the run actually starts — importing this module never touches the SDK.

    NEVER the CLI default. A real run is an explicit CampaignRunner.run(AgenticBackend(...))."""
    name = "agentic"

    def __init__(self, *, out_dir: str | Path | None = None, model: str = "claude-opus-4-8",
                 workers: int = 4, client=None, client_factory=None,
                 max_iters: int = 40, gate_critic: bool = False, offline: bool = False):
        self.out_dir = Path(out_dir) if out_dir else (REPO / "_recuration_output")
        self.model = model
        self.workers = max(1, int(workers))
        self._client = client
        self._client_factory = client_factory
        self.max_iters = max_iters
        self.gate_critic = gate_critic
        self.offline = offline
        self._shared_real = None

    def _client_for(self):
        if self._client_factory is not None:
            return self._client_factory()
        if self._client is not None:
            return self._client
        if self._shared_real is None:               # real run: build once, share (thread-safe)
            import anthropic
            self._shared_real = anthropic.Anthropic()
        return self._shared_real

    def run(self, items, build_request=None, parse_result=None) -> dict[str, ItemResult]:
        # build_request / parse_result are unused here (vestigial Backend-Protocol slots);
        # the agentic loop is defined by curate_engine, not per-request.
        from concurrent.futures import ThreadPoolExecutor, as_completed

        sys.path.insert(0, str(Path(__file__).resolve().parent))   # ensure scripts/ importable
        import curate_engine

        paths_dir = self.out_dir / "paths"
        cache_root = self.out_dir / "cache"
        run_id = uuid.uuid4().hex[:12]

        def _one(w: WorkItem) -> ItemResult:
            out_path = paths_dir / f"{w.id}.yaml"
            cache_dir = cache_root / w.id
            try:
                res = curate_engine.curate_one(
                    w, model=self.model, cache_dir=cache_dir, out_path=out_path,
                    client=self._client_for(), max_iters=self.max_iters, run_id=run_id,
                    offline=self.offline, gate_critic=self.gate_critic)
                err = res.error or (None if res.ok
                                    else f"not accepted (gate={res.gate_verdict}, wrote={res.wrote_yaml})")
                return ItemResult(w.id, ok=res.ok, error=err)
            except Exception as e:
                return ItemResult(w.id, ok=False, error=f"{type(e).__name__}: {e}")

        out: dict[str, ItemResult] = {}
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futs = {ex.submit(_one, w): w for w in items}
            for fut in as_completed(futs):
                w = futs[fut]
                out[w.id] = fut.result()
        return out


# ── runner ──────────────────────────────────────────────────────────────────

@dataclass
class CampaignRunner:
    model: str = "claude-opus-4-8"
    status: StatusStore = field(default_factory=StatusStore.load)

    def plan(self) -> tuple[list[WorkItem], list[WorkItem]]:
        """(all_items, pending_items) — dry-run view, submits nothing."""
        allw = enumerate_work()
        return allw, self.status.pending(allw)

    def run(self, backend: Backend, *, build_request=None, parse_result=None,
            limit: int | None = None) -> dict[str, ItemResult]:
        """Dispatch pending items through the backend, stamp provenance, persist status.
        Resumable + idempotent: already-done items are skipped."""
        _, pending = self.plan()
        if limit is not None:
            pending = pending[:limit]
        run_id = uuid.uuid4().hex[:12]
        for w in pending:
            self.status.mark(w.id, "submitted", run_id=run_id)
        self.status.save()

        results = backend.run(pending, build_request, parse_result)

        prov = make_provenance(self.model, run_id)
        for w in pending:
            res = results.get(w.id)
            if res is not None and res.ok:
                self.status.mark(w.id, "done", provenance=prov)
            else:
                self.status.mark(w.id, "failed", error=(res.error if res else "no result"))
        self.status.save()
        return results


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="print campaign status and exit")
    ap.add_argument("--stub", action="store_true",
                    help="run pending items through the offline StubBackend (no API, no curation)")
    ap.add_argument("--limit", type=int, default=None, help="cap items processed this run")
    args = ap.parse_args()

    runner = CampaignRunner()
    allw, pending = runner.plan()

    if args.status:
        c = runner.status.counts()
        print(f"Campaign: {len(allw)} records total · {len(pending)} pending")
        print("  status:", ", ".join(f"{k}={v}" for k, v in c.items() if v))
        return 0

    if args.stub:
        results = runner.run(StubBackend(), limit=args.limit)
        ok = sum(1 for r in results.values() if r.ok)
        print(f"[stub] processed {len(results)} · ok {ok} · status file: {STATUS_FILE.name}")
        return 0

    # Default: dry-run plan. Never curates.
    print(f"DRY RUN — {len(allw)} records, {len(pending)} pending (nothing submitted).")
    print("  --stub    run the framework offline (StubBackend)")
    print("  --status  show progress")
    print("  A real run is an explicit CampaignRunner.run(AgenticBackend(...)) call.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
