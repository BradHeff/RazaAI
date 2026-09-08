"""RazaAI stress test : long mixed sessions, conversation <-> code changes (.x)."""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RESULTS = Path("evals/stress/results")
BOILERPLATE = re.compile(r"how can i (?:assist|help) you today|i apologi[sz]e (?:if|for)|feel free to ask|as an ai", re.I)


def _git(ws, *args):
    return subprocess.run(["git", "-c", "user.name=s", "-c", "user.email=s@s", *args], cwd=ws, capture_output=True, text=True)


def make_workspace():
    ws = Path(tempfile.mkdtemp(prefix="razaai-stress-"))
    (ws / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (ws / "test_calc.py").write_text(
        "import unittest\n\nfrom calc import add\n\n\nclass TestCalc(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\n\nif __name__ == '__main__':\n    unittest.main()\n",
        encoding="utf-8")
    # Starts GREEN; the fix-a-failing-test step breaks it deliberately just before asking for the fix
    (ws / "slug.py").write_text("import re\n\n\ndef slugify(text):\n    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n", encoding="utf-8")
    (ws / "test_slug.py").write_text(
        "import unittest\n\nfrom slug import slugify\n\n\nclass T(unittest.TestCase):\n"
        "    def test_trim(self):\n        self.assertEqual(slugify('  Hi, World!  '), 'hi-world')\n", encoding="utf-8")
    _git(ws, "init", "-q"); _git(ws, "add", "-A"); _git(ws, "commit", "-q", "-m", "fixture")
    return ws


class Turn:
    def __init__(self, cycle, step, kind, prompt):
        self.cycle, self.step, self.kind, self.prompt = cycle, step, kind, prompt
        self.answer = ""
        self.seconds = 0.0
        self.prompt_tokens = self.output_tokens = None
        self.estimate = None
        self.compactions = 0
        self.overflow = False
        self.history_removed = 0
        self.violations = []      # Application invariants broken -> exit 1
        self.model_failures = []  # the model's plan failed verification and was rolled back honestly
        self.model = ""
        self.avail_mb = self.swap_mb = None
        self.error = ""

    def row(self):
        return {"cycle": self.cycle, "step": self.step, "kind": self.kind, "model": self.model, "prompt": self.prompt[:60],
                "seconds": round(self.seconds, 1), "prompt_tokens": self.prompt_tokens, "output_tokens": self.output_tokens,
                "estimate": self.estimate, "compactions": self.compactions, "history_removed": self.history_removed,
                "overflow": self.overflow, "avail_mb": self.avail_mb, "swap_mb": self.swap_mb,
                "violations": "; ".join(self.violations), "model_failures": "; ".join(self.model_failures), "error": self.error,
                # Keep the full answer whenever something went wrong, so the CSV is diagnosable
                "answer": self.answer.replace("\n", " ")[: (2500 if self.violations or self.model_failures or self.error or self.kind in {"code-propose", "code-fix"} else 160)]}


def run_turn(agent, turn: Turn, timeout: float):
    from app.runtime_health import memory_snapshot
    buf = io.StringIO()
    result = {}

    def _go():
        try:
            with contextlib.redirect_stdout(buf):
                result["answer"] = agent.ask(turn.prompt)
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"

    started = time.monotonic()
    worker = threading.Thread(target=_go, daemon=True)
    worker.start()
    worker.join(timeout)
    turn.seconds = time.monotonic() - started
    if worker.is_alive():
        turn.error = f"TIMEOUT after {timeout}s"
        turn.violations.append("turn exceeded timeout")
        return
    turn.error = result.get("error", "")
    turn.answer = str(result.get("answer") or "")
    if turn.error:
        turn.violations.append(f"exception: {turn.error[:100]}")
    if not turn.answer.strip() and not turn.error:
        turn.violations.append("empty answer")
    diag = buf.getvalue()
    turn.compactions = diag.count("[Context] compacted prompt")
    m = re.findall(r"history_removed=(\d+)", diag)
    turn.history_removed = sum(int(x) for x in m)
    turn.overflow = "exceeded context" in diag or "context overflow" in diag.lower()
    if turn.overflow:
        turn.violations.append("context overflow retry occurred")
    usage = getattr(getattr(agent, "client", None), "last_usage", {}) or {}
    turn.prompt_tokens, turn.output_tokens = usage.get("prompt_tokens"), usage.get("output_tokens")
    turn.model = getattr(getattr(agent, "client", None), "model", "")
    snap = memory_snapshot()
    turn.avail_mb, turn.swap_mb = snap.get("available_mb"), snap.get("swap_used_mb")


def classify_approve(turn, label, expect_file=None, ws=None):
    """PASS -> ok; honest rollback -> model failure; anything else -> app violation."""
    a = turn.answer
    if "Verification: PASS" in a:
        if expect_file and ws and expect_file not in (ws / "calc.py").read_text(encoding="utf-8"):
            turn.violations.append(f"{label}: reported PASS but {expect_file} is not on disk")
        if "Sandbox:" not in a:
            turn.violations.append(f"{label}: report lacks Sandbox line")
        return True
    if "Verification: FAILED" in a and "restored" in a:
        fail_line = next((l for l in a.splitlines() if l.strip().startswith("- FAIL")), "")
        turn.model_failures.append(f"{label}: plan failed verification and was rolled back ({fail_line[:160]})")
        return False
    if "did not change the workspace" in a:
        turn.model_failures.append(f"{label}: no applicable plan ({a[:160]})")
        return False
    turn.violations.append(f"{label}: unexpected approve outcome: {a[:120]}")
    return False


GREEN_SLUG = "import re\n\n\ndef slugify(text):\n    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n"


def proposal_ok(turn):
    """True if the proposal is complete. A gapped proposal is a MODEL failure and must be rejected."""
    a = turn.answer
    if "Proposed changes" not in a:
        return False
    if "does NOT fully satisfy" in a:
        gaps = a.split("does NOT fully satisfy the request:", 1)[1].split("You can `/approve`", 1)[0]
        turn.model_failures.append("proposal incomplete after retry: " + " ".join(gaps.split())[:220])
        return False
    return True


def check_identity(turn):
    low = turn.answer.casefold()
    if "brad heffernan" not in low:
        turn.violations.append("identity: creator missing")
    if turn.kind == "identity-when" and "2019" not in low:
        turn.violations.append("identity: 2019 missing")


def check_voice(turn, coder_active):
    if coder_active and BOILERPLATE.search(turn.answer):
        turn.violations.append("voice: customer-service boilerplate from coder model")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--code-model", default=os.getenv("RAZAAI_CODE_MODEL", ""), help="model for the coding session (default: env / conversation model)")
    parser.add_argument("--swap-models", action="store_true", help="also run a conversation-model agent between coding turns to force Ollama swaps")
    parser.add_argument("--conversation-only", action="store_true")
    parser.add_argument("--turn-timeout", type=float, default=300.0)
    parser.add_argument("--keep-workspace", action="store_true")
    args = parser.parse_args(argv)

    if args.code_model:
        os.environ["RAZAAI_CODE_MODEL"] = args.code_model
    os.environ.setdefault("RAZAAI_CODE_AUTO_APPROVE", "0")
    from app.config import APP_VERSION, OLLAMA_MODEL
    from app.evaluation.capabilities import _hermetic_state, _restore_state
    from app.agent import RazaAgent

    ws = make_workspace()
    previous = _hermetic_state()  # Fresh memory/feedback state so cycles are comparable
    turns: list[Turn] = []
    started_all = time.monotonic()
    print("=" * 78)
    print(f"RazaAI stress  app={APP_VERSION} host={socket.gethostname()} conversation={OLLAMA_MODEL} code={args.code_model or OLLAMA_MODEL} cycles={args.cycles} swap={args.swap_models}")
    print("=" * 78)
    try:
        coder = RazaAgent(workspace_root=None if args.conversation_only else ws)
        coder_active = bool(getattr(coder, "code_model_active", False))
        conv = RazaAgent() if args.swap_models else None

        def T(cycle, step, kind, prompt, agent=None, timeout=None):
            t = Turn(cycle, step, kind, prompt)
            run_turn(agent or coder, t, timeout or args.turn_timeout)
            turns.append(t)
            return t

        for c in range(1, args.cycles + 1):
            n = c  # Function name suffix keeps every coding request distinct
            print(f"--- cycle {c}/{args.cycles}")
            check_identity(T(c, 1, "identity", "who made you?")); check_voice(turns[-1], coder_active)
            check_identity(T(c, 2, "identity-when", "when were you created?")); check_voice(turns[-1], coder_active)
            t = T(c, 3, "challenge", "liar"); check_voice(t, coder_active)
            check_identity(T(c, 4, "identity", "who made you"))

            if not args.conversation_only:
                before = (ws / "calc.py").read_text(encoding="utf-8")
                # The suite must be GREEN before a coding request: reset the fix-step fixture
                (ws / "slug.py").write_text(GREEN_SLUG, encoding="utf-8")
                t = T(c, 5, "code-propose", f"add a function named mul{n}(a, b) that returns a * b to calc.py and a unittest for it")
                if "Proposed changes" not in t.answer and "did not change the workspace" not in t.answer:
                    t.violations.append("no proposal returned for a mutation request")
                if proposal_ok(t):
                    t = T(c, 6, "code-approve", "/approve")
                    classify_approve(t, "first approve", expect_file=f"def mul{n}", ws=ws)
                elif "Proposed changes" in t.answer:
                    T(c, 6, "code-reject", "/reject")

            if conv is not None:
                t = T(c, 7, "swap-conversation", "in two sentences, what does a default gateway do?", agent=conv)
                check_voice(t, False)
            t = T(c, 8, "local-fact", "what is the default gateway on this machine?")
            if "Default gateway:" not in t.answer:
                t.violations.append("local fact not answered from tool evidence")
            t = T(c, 9, "advice", "a FortiGate IPsec tunnel is down, give me a systematic troubleshooting order")
            if not re.search(r"phase\s*2", t.answer, re.I):
                t.violations.append("advice: IPsec answer lacks phase 2")
            check_voice(t, coder_active)

            if not args.conversation_only:
                before_calc = (ws / "calc.py").read_text(encoding="utf-8")
                t = T(c, 10, "code-propose", f"add a function named neg{n}(a) that returns -a to calc.py and a unittest for it")
                if proposal_ok(t):
                    t = T(c, 11, "code-approve", "/approve")
                    second_ok = classify_approve(t, "second approve", expect_file=f"def neg{n}", ws=ws)
                else:
                    if "Proposed changes" in t.answer:
                        T(c, 11, "code-reject", "/reject")
                    second_ok = False
                if second_ok:  # Undo is only meaningful after an applied task
                    t = T(c, 12, "code-undo", "/undo")
                    if (ws / "calc.py").read_text(encoding="utf-8") != before_calc:
                        t.violations.append("undo did not restore calc.py byte-for-byte")
                    t = T(c, 13, "code-propose", f"add a function named neg{n}(a) that returns -a to calc.py and a unittest for it")
                    if proposal_ok(t):
                        t = T(c, 14, "code-approve", "/approve")
                        reapplied = classify_approve(t, "re-apply approve", expect_file=f"def neg{n}", ws=ws)
                    else:
                        if "Proposed changes" in t.answer:
                            T(c, 14, "code-reject", "/reject")
                        reapplied = False
                else:
                    reapplied = False
                dirty_before = bool(_git(ws, "status", "--short").stdout.strip())
                t = T(c, 15, "code-checkpoint", f"/checkpoint cycle {c}")
                branch = _git(ws, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
                if not branch.startswith("raza/"):
                    t.violations.append(f"checkpoint branch is {branch!r}, not raza/*")
                if dirty_before and "nothing to commit" in t.answer:
                    t.violations.append("workspace was dirty but checkpoint found nothing to commit")
                if _git(ws, "status", "--short").stdout.strip():
                    t.violations.append("workspace still dirty after checkpoint")
                t = T(c, 16, "git-branch", "git branch")
                if "raza/" not in t.answer:
                    t.violations.append("git branch answer does not show the raza branch")

            t = T(c, 17, "memory-remember", f"remember that my lab switch for cycle {c} is an Aruba 2930F on VLAN {100 + c}")
            t = T(c, 18, "memory-recall", f"what do you remember about my lab switch for cycle {c}?")
            if f"{100 + c}" not in t.answer and "2930F" not in t.answer:
                t.violations.append("memory recall missing the remembered fact")

            if not args.conversation_only:
                (ws / "slug.py").write_text("import re\n\n\ndef slugify(text):\n    return re.sub(r'[^a-z0-9]+', '-', text.lower())\n", encoding="utf-8")
                t = T(c, 19, "code-fix", "the test suite fails; fix the code in slug.py so test_trim passes without changing the tests")
                if proposal_ok(t):
                    t = T(c, 20, "code-approve", "/approve")
                    classify_approve(t, "fix-failing-test approve")
                elif "Proposed changes" in t.answer:
                    T(c, 20, "code-reject", "/reject")
                elif "did not change the workspace" in t.answer:
                    t.model_failures.append("fix request: planner produced no applicable plan")
                else:
                    t.violations.append("fix request produced neither a proposal nor an honest refusal")

            t = T(c, 21, "closing-conversation", "thanks, that's all for now")
            check_voice(t, coder_active)
            bad = [x for x in turns if x.cycle == c and x.violations]
            mf = [x for x in turns if x.cycle == c and x.model_failures]
            print(f"    cycle {c}: {len([x for x in turns if x.cycle == c])} turns, {len(bad)} app violations, {len(mf)} model failures, "
                  f"{sum(x.seconds for x in turns if x.cycle == c):.0f}s")
            for x in bad:
                print(f"      ! APP step {x.step} {x.kind}: {'; '.join(x.violations)}")
                print(f"        answer: {x.answer.replace(chr(10), ' ')[:300]}")
            for x in mf:
                print(f"      ~ MODEL step {x.step} {x.kind}: {'; '.join(x.model_failures)}")
    finally:
        _restore_state(previous)
        if not args.keep_workspace:
            shutil.rmtree(ws, ignore_errors=True)
        else:
            print(f"workspace kept: {ws}")

    total = time.monotonic() - started_all
    secs = sorted(t.seconds for t in turns)
    p50 = secs[len(secs) // 2] if secs else 0
    p95 = secs[int(len(secs) * 0.95)] if secs else 0
    violations = sum(1 for t in turns if t.violations)
    model_failures = sum(1 for t in turns if t.model_failures)
    code_turns = sum(1 for t in turns if t.kind in {"code-propose", "code-fix"})
    ratios = [(t.prompt_tokens / t.estimate) for t in turns if t.prompt_tokens and t.estimate]
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    tag = (args.code_model or OLLAMA_MODEL).replace(":", "_").replace("/", "_")
    csv_path = RESULTS / f"stress-{tag}-{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(turns[0].row().keys()) if turns else ["empty"])
        w.writeheader()
        for t in turns:
            w.writerow(t.row())
    md = [f"# Stress — {tag} — {stamp}", "",
          f"- app {APP_VERSION}, host {socket.gethostname()}, cycles {args.cycles}, swap-models {args.swap_models}",
          f"- turns {len(turns)}, **app violations {violations}**, model failures {model_failures} of {code_turns} coding requests ({(model_failures / code_turns * 100) if code_turns else 0:.0f}%), total {total:.0f}s, p50 {p50:.1f}s, p95 {p95:.1f}s",
          f"- compactions {sum(t.compactions for t in turns)}, history removed {sum(t.history_removed for t in turns)}, overflow retries {sum(t.overflow for t in turns)}",
          f"- memory: min available {min((t.avail_mb for t in turns if t.avail_mb is not None), default='?')} MB, max swap {max((t.swap_mb for t in turns if t.swap_mb is not None), default='?')} MB",
          "", "| cycle | step | kind | model | s | in | out | app violations | model failures |", "|---|---|---|---|---|---|---|---|---|"]
    for t in turns:
        md.append(f"| {t.cycle} | {t.step} | {t.kind} | {t.model} | {t.seconds:.1f} | {t.prompt_tokens} | {t.output_tokens} | {'; '.join(t.violations) or (t.error[:60] if t.error else '')} | {'; '.join(t.model_failures)} |")
    md_path = csv_path.with_suffix(".md")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("=" * 78)
    print(f"turns {len(turns)}  APP violations {violations}  MODEL failures {model_failures}/{code_turns} coding requests  p50 {p50:.1f}s  p95 {p95:.1f}s  total {total:.0f}s  overflow {sum(t.overflow for t in turns)}")
    print(f"CSV:      {csv_path}\nMarkdown: {md_path}")
    print("=" * 78)
    return 0 if violations == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
