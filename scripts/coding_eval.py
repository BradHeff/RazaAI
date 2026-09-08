"""RazaAI coding evaluation harness."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import socket

from app.coding import WorkspaceCoworker
from app.config import APP_VERSION, CODE_MODEL
from app.evaluation.capabilities import _hermetic_state, _restore_state
from app.ollama_client import OllamaClient
from app.tools.workspace import WorkspaceManager
from evals.coding.tasks import TASKS, available_tasks

RESULTS_DIR = Path("evals/coding/results")


class _CountingClient:
    """Wraps a chat client to count planner calls and accumulate token usage."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.retry_triggered = False

    def chat(self, messages, tools=None, **kwargs):
        self.calls += 1
        if any("PREVIOUS PLAN WAS INCOMPLETE" in m.get("content", "") for m in messages):
            self.retry_triggered = True
        try:
            try:
                return self.inner.chat(messages, tools=tools, **kwargs)
            except TypeError:
                return self.inner.chat(messages, tools=tools)
        finally:  # Count tokens even when the caller later rejects the reply
            usage = getattr(self.inner, "last_usage", {}) or {}
            self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.output_tokens += int(usage.get("output_tokens") or 0)


def run_task(task, *, client_factory, context_window, keep_workspace=False):
    ws = Path(tempfile.mkdtemp(prefix=f"razaai-eval-{task.id.replace('.', '-')}-"))
    task.setup(ws)
    client = _CountingClient(client_factory())
    coworker = WorkspaceCoworker(client=client, manager=WorkspaceManager(ws), context_window=context_window,
                                 require_approval=False)
    previous = _hermetic_state()
    started = time.monotonic()
    try:
        report = coworker.handle(task.request)
    except Exception as exc:  # noqa: BLE001 - an exception is a failed task, not a crashed eval
        import traceback
        tail = traceback.format_exc().strip().splitlines()[-4:]
        report = f"EXCEPTION: {type(exc).__name__}: {exc} | " + " | ".join(l.strip() for l in tail)
    finally:
        _restore_state(previous)
    elapsed = time.monotonic() - started
    try:
        passed, detail = task.check(ws)
    except Exception as exc:  # noqa: BLE001
        passed, detail = False, f"checker error: {type(exc).__name__}: {exc}"
    if report.startswith("EXCEPTION:"):
        detail = report[:300]  # An application exception must never hide behind a checker message
    row = {
        "task": task.id,
        "language": task.language,
        "passed": passed,
        "detail": detail.replace("\n", " ")[:300],
        "verification": "PASS" if "Verification: PASS" in report else ("ROLLBACK" if "restored" in report else "NONE"),
        "first_plan_ok": not client.retry_triggered,
        "planner_calls": client.calls,
        "prompt_tokens": client.prompt_tokens,
        "output_tokens": client.output_tokens,
        "elapsed_s": round(elapsed, 1),
        "workspace": str(ws) if keep_workspace else "",
        "report_head": report.splitlines()[0][:120] if report else "",
    }
    if not keep_workspace:
        shutil.rmtree(ws, ignore_errors=True)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=CODE_MODEL)
    parser.add_argument("--ollama-url", default=os.getenv("RAZAAI_OLLAMA_HOST", "http://127.0.0.1:11434"))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--tasks", default="", help="comma-separated task ids (default: all available)")
    parser.add_argument("--context-window", type=int, default=None)
    parser.add_argument("--keep-workspaces", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--client-factory", default=None, help=argparse.SUPPRESS)  # Tests inject a fake
    args = parser.parse_args(argv)

    tasks = available_tasks()
    if args.list:
        for t in TASKS:
            missing = [b for b in t.requires if shutil.which(b) is None]
            print(f"{t.id:28} {t.language:10} {'(needs ' + ','.join(missing) + ')' if missing else ''}  {t.request}")
        return 0
    if args.tasks:
        wanted = {t.strip() for t in args.tasks.split(",") if t.strip()}
        tasks = [t for t in tasks if t.id in wanted]
        if not tasks:
            print("no matching tasks"); return 2

    if args.client_factory:
        module, _, name = args.client_factory.rpartition(":")
        import importlib
        client_factory = getattr(importlib.import_module(module), name)
        context_window = args.context_window or 8192
    else:
        def client_factory():
            return OllamaClient(host=args.ollama_url, model=args.model)
        probe = OllamaClient(host=args.ollama_url, model=args.model)
        context_window = args.context_window or probe.detect_context_window(fallback=4096)

    runs = max(1, args.runs)
    print("=" * 78)
    print(f"RazaAI Coding Evaluation  app={APP_VERSION}  host={socket.gethostname()}  model={args.model}  tasks={len(tasks)}  runs={runs}  ctx={context_window}")
    print("=" * 78)

    rows = []
    for task in tasks:
        outcomes = []
        for run_index in range(runs):
            row = run_task(task, client_factory=client_factory, context_window=context_window,
                           keep_workspace=args.keep_workspaces)
            row["run"] = run_index + 1
            row["model"] = args.model
            rows.append(row)
            outcomes.append(row)
            status = "PASS" if row["passed"] else "FAIL"
            print(f"[{status}] {task.id:28} run {row['run']}  {row['elapsed_s']:6.1f}s  in {row['prompt_tokens']:5d} out {row['output_tokens']:4d}  "
                  f"planner x{row['planner_calls']}  verify={row['verification']}  {'' if row['passed'] else row['detail'][:90]}")
        stable = all(o["passed"] for o in outcomes)
        if runs > 1 and not stable and any(o["passed"] for o in outcomes):
            print(f"       UNSTABLE: {task.id} passed {sum(o['passed'] for o in outcomes)}/{runs}")

    by_task = {}
    for row in rows:
        by_task.setdefault(row["task"], []).append(row["passed"])
    stable_pass = sum(all(v) for v in by_task.values())
    any_pass = sum(any(v) for v in by_task.values())
    first_plan = sum(1 for r in rows if r["first_plan_ok"] and r["passed"]) / max(1, len(rows))
    total_time = sum(r["elapsed_s"] for r in rows)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = args.model.replace(":", "_").replace("/", "_")
    fd, result_name = tempfile.mkstemp(prefix=f"coding-{safe_model}-{stamp}-", suffix=".csv", dir=RESULTS_DIR)
    os.close(fd)
    csv_path = Path(result_name)
    fields = ["model", "task", "language", "run", "passed", "first_plan_ok", "verification", "planner_calls",
              "prompt_tokens", "output_tokens", "elapsed_s", "detail", "report_head", "workspace"]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})
    md_path = csv_path.with_suffix(".md")
    lines = [f"# Coding eval: {args.model}, {stamp}", "",
             f"- tasks: {len(by_task)}  runs per task: {runs}",
             f"- **stable pass (every run): {stable_pass}/{len(by_task)}**  any-run pass: {any_pass}/{len(by_task)}",
             f"- first-plan success rate (no completeness retry, task passed): {first_plan:.0%}",
             f"- total wall-clock: {total_time:.0f}s  mean per task-run: {total_time / max(1, len(rows)):.1f}s",
             f"- tokens: prompt {sum(r['prompt_tokens'] for r in rows)}  output {sum(r['output_tokens'] for r in rows)}", "",
             "| task | run | passed | first plan ok | verify | planner calls | s | in | out | detail |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['task']} | {r['run']} | {'PASS' if r['passed'] else 'FAIL'} | {'PASS' if r['first_plan_ok'] else 'RETRY'} | {r['verification']} | {r['planner_calls']} | {r['elapsed_s']} | {r['prompt_tokens']} | {r['output_tokens']} | {r['detail'][:80] if not r['passed'] else ''} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 78)
    print(f"Stable pass: {stable_pass}/{len(by_task)}   any-run pass: {any_pass}/{len(by_task)}   first-plan: {first_plan:.0%}   time: {total_time:.0f}s")
    print(f"CSV:      {csv_path}")
    print(f"Markdown: {md_path}")
    print("=" * 78)
    return 0 if stable_pass == len(by_task) else 1


if __name__ == "__main__":
    sys.exit(main())
