"""Build a coder QLoRA seed from RazaAI's own failures."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import os

from app.config import BASE_DIR

SEED_DIR = Path("training/coder_v2_seed")


def trace_root():
    return Path(os.getenv("RAZAAI_CODER_TRACE_DIR") or (BASE_DIR / "data" / "coder_traces"))


def load_traces():
    root = trace_root()
    records = []
    for path in sorted(root.glob("*.jsonl")) if root.is_dir() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
    return records


def pair_outcomes(records):
    """Attach the next outcome record for the same request to each plan record."""
    plans = []
    pending = {}
    for r in records:
        if r.get("kind") == "plan":
            pending.setdefault(r.get("request"), []).append(r)
            plans.append(r)
        elif r.get("kind") == "outcome":
            queue = pending.get(r.get("request")) or []
            for p in queue:
                p.setdefault("outcome", r)
            pending[r.get("request")] = []
    return plans


_ADD_RE = re.compile(r"add a function named (\w+)\(([^)]*)\) that returns (.+?) to (\S+\.py)(?: and a unittest for it)?", re.I)


def _anchor(prompt, label_prefix):
    m = re.search(re.escape(label_prefix) + r'.*?old_text=("(?:[^"\\]|\\.)*")', prompt)
    return json.loads(m.group(1)) if m else None


def _import_line(prompt, module):
    m = re.search(rf"^(from {re.escape(module)} import [^\n]+)$", prompt, re.M)
    return m.group(1) + "\n" if m else None


def autocorrect(pending_path):
    if not pending_path.is_file():
        print("nothing pending"); return 1
    kept, filled, dropped = [], 0, 0
    for line in pending_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        plan = rec.get("model_plan") or {}
        # Synthetic test-suite traces (a deliberately wrong 'return a') are not teaching material
        if any("return a\n" == str(f.get("content", ""))[-9:] for f in plan.get("files") or []):
            dropped += 1; continue
        m = _ADD_RE.search(rec.get("request") or "")
        if m and not rec.get("corrected_plan"):
            name, args, expr, target = m.groups()
            prompt = rec.get("user") or ""
            module = Path(target).stem
            files = [{"path": target, "mode": "append", "content": f"def {name}({args}):\n    return {expr}\n"}]
            test_file = f"test_{module}.py"
            imp = _import_line(prompt, module)
            if imp and name not in imp:
                files.append({"path": test_file, "mode": "patch", "old_text": imp, "new_text": imp.rstrip("\n") + f", {name}\n"})
            cls = re.search(r"add a method to class (\w+): patch old_text=", prompt)
            anchor = _anchor(prompt, f"add a method to class {cls.group(1)}") if cls else None
            argc = len([a for a in args.split(",") if a.strip()])
            sample = "2, 3" if argc == 2 else "3"
            expect = {"a * b": "6", "a + b": "5", "-a": "-3", "a - b": "-1"}.get(expr.strip(), None)
            assertion = f"self.assertEqual({name}({sample}), {expect})" if expect else f"self.assertIsNotNone({name}({sample}))"
            if anchor:
                files.append({"path": test_file, "mode": "patch", "old_text": anchor,
                              "new_text": anchor.rstrip("\n") + f"\n\n    def test_{name}(self):\n        {assertion}\n"})
            rec["corrected_plan"] = {"files": files, "summary": f"add {name} to {target} and test_{name} to {test_file}"}
            rec["corrected_by"] = "autocorrect (add-function family)"
            filled += 1
        kept.append(rec)
    pending_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    print(f"filled {filled} corrected_plan(s), dropped {dropped} synthetic record(s), {len(kept)} record(s) remain; "
          f"{sum(1 for r in kept if not r.get('corrected_plan'))} still need a human plan")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--include-passed", action="store_true", help="also export plans that passed, as positive examples")
    parser.add_argument("--finalize", action="store_true", help="emit training/coder_v2_seed/coder_v2.jsonl from records with corrected_plan")
    parser.add_argument("--autocorrect", action="store_true",
                        help="fill corrected_plan for the 'add a function named X(...) that returns EXPR to F and a unittest' family "
                             "using the PATCH ANCHORS in each prompt; records from the test suite (return a) are dropped")
    args = parser.parse_args(argv)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    pending_path = SEED_DIR / "pending.jsonl"

    if args.autocorrect:
        return autocorrect(pending_path)

    if args.finalize:
        out = []
        if pending_path.is_file():
            for line in pending_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                plan = rec.get("corrected_plan") or (rec.get("model_plan") if rec.get("passed") else None)
                if not plan:
                    continue
                out.append({"messages": [
                    {"role": "system", "content": rec["system"]},
                    {"role": "user", "content": rec["user"]},
                    {"role": "assistant", "content": json.dumps(plan, ensure_ascii=False)},
                ]})
        final = SEED_DIR / "coder_v2.jsonl"
        final.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out), encoding="utf-8")
        print(f"{len(out)} training example(s) -> {final}")
        return 0

    plans = pair_outcomes(load_traces())
    if not plans:
        print(f"no planner traces under {trace_root()} — run with RAZAAI_CODER_TRACE=1 first")
        return 1
    existing = set()
    if pending_path.is_file():
        for line in pending_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.add(json.loads(line).get("key"))
    added = 0
    with pending_path.open("a", encoding="utf-8") as fh:
        for p in plans:
            outcome = p.get("outcome") or {}
            gapped = bool(p.get("gaps"))
            failed = outcome and not outcome.get("passed", True)
            if not (gapped or failed or args.include_passed):
                continue
            key = f"{p.get('ts')}|{hash(p.get('user', ''))}"
            if key in existing:
                continue
            try:
                model_plan = json.loads(p.get("reply") or "{}")
            except ValueError:
                model_plan = {"raw": p.get("reply")}
            rec = {
                "key": key, "ts": p.get("ts"), "model": p.get("model"), "request": p.get("request"),
                "system": p.get("system"), "user": p.get("user"),
                "model_plan": model_plan,
                "failure": list(p.get("gaps") or []) + [c for c in (outcome.get("checks") or []) if str(c).lstrip("- ").startswith("FAIL")],
                "passed": bool(outcome) and bool(outcome.get("passed")) and not gapped,
                "corrected_plan": None,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            added += 1
    print(f"{added} new record(s) -> {pending_path}  (fill corrected_plan, then --finalize)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
