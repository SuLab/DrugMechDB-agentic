# Evaluation CLI (`scripts/eval_cli.py`)

One reusable entry point for the evaluation harness. It unifies the two previously
separate pieces — `scripts/run_phase3_eval.py` (scoring) and
`experiments/opus_vs_sonnet/run_arm.py` (an older standalone curation-arm runner) —
behind three subcommands. Each subcommand is a thin **wrapper** around existing code;
no scoring or curation logic is duplicated.

The canonical curation loop is now `scripts/curate_engine.py` (`curate_one`). New eval
curation goes through the engine (directly or via `eval_cli curate`); `run_arm.py`
remains only as the historical two-arm runner that produced the committed
`experiments/opus_vs_sonnet/opus|sonnet` artifacts.

Build-only: importing the module does nothing external. `score` and `compare` are
offline. `curate` defaults to a dry run — a real curation (which builds a real client
and calls the API) happens only with the explicit `--run` flag.

## Subcommands

### `score` — QC scoring over an outputs dir
Wraps `run_phase3_eval.py`'s scoring (the 4-layer QC gate + tabulation). With no
overrides it reproduces the Phase-3 behavior; `--outputs-dir` / `--pairs-file` point it
at any dir of `<pair_id>.yaml` outputs.

```bash
.venv-py310/bin/python scripts/eval_cli.py score            # default Phase-3 set
.venv-py310/bin/python scripts/eval_cli.py score P01 P02 \
    --outputs-dir <dir> --pairs-file <pairs.yaml> --report
```

### `curate` — curate eval pairs via the canonical engine
Drives `curate_engine.curate_one` over selected pairs into an isolated `--out-dir`
(`paths/` + per-pair `cache/`; never `kb/paths`). Default is a dry-run plan.

```bash
# dry run (no client, no API) — prints the plan and the real-run recipe
.venv-py310/bin/python scripts/eval_cli.py curate --out-dir <dir> --pairs P01,P02
# real run (builds a real client, calls the API) — explicit and deliberate
.venv-py310/bin/python scripts/eval_cli.py curate --out-dir <dir> --pairs P01,P02 --run
```

A real run writes `<out-dir>/run_summary.json`; score its YAMLs with
`eval_cli.py score --outputs-dir <out-dir>/paths`.

### `compare` — two-arm head-to-head
Reads the committed `run_summary.json` / `analysis.json` shapes and prints a per-arm
summary plus a head-to-head (pass agreement, cost on shared pairs, and a winner by pass
rate then cost). Pass/fail is available from `analysis.json`; a bare `run_summary.json`
carries metrics only (cost / iters / wall).

```bash
# a single combined analysis file (both arms)
.venv-py310/bin/python scripts/eval_cli.py compare experiments/opus_vs_sonnet/analysis.json
# or two arm dirs / run_summary.json files
.venv-py310/bin/python scripts/eval_cli.py compare <arm_a> <arm_b> --labels a,b --json out.json
```
