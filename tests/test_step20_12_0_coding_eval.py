"""RazaAI: coding eval harness: checkers are satisfiable and discriminating, results are recorded, and a dedicated coder model can be selected for coding sessions."""

import csv
import importlib
import os
import subprocess
import sys
from pathlib import Path

from evals.coding.tasks import TASKS, available_tasks


def main():
    print("=" * 78)
    print("RazaAI Step 20.12.0 Coding Evaluation Harness")
    print("=" * 78)

    assert len(TASKS) >= 9
    ids = [t.id for t in TASKS]
    assert len(ids) == len(set(ids))
    tags = {tag for t in TASKS for tag in t.tags}
    assert {
        "add",
        "test",
        "edit",
        "exploration",
        "refactor",
        "multi-file",
        "fix",
        "docs",
        "trap",
    } <= tags
    print(
        f"[PASS] {len(TASKS)} deterministic tasks covering add/edit/refactor/fix/docs/trap/exploration"
    )

    env = dict(os.environ, PYTHONPATH=str(Path.cwd()))
    golden = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.coding_eval",
            "--client-factory",
            "evals.coding.reference_client:golden_factory",
            "--runs",
            "1",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    assert golden.returncode == 0, golden.stdout[-1500:] + golden.stderr[-800:]
    n = len(available_tasks())
    assert (
        f"Stable pass: {n}/{n}" in golden.stdout and "first-plan: 100%" in golden.stdout
    ), golden.stdout[-600:]
    print(
        "[PASS] a correct reference planner passes every available task on the first plan (checkers are satisfiable)"
    )

    wrong = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.coding_eval",
            "--client-factory",
            "evals.coding.reference_client:wrong_factory",
            "--tasks",
            "py.add_with_test,py.fix_failing_test,docs.readme_install,py.default_arg_trap",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    # The target-authority guard strips the wrong planner's
    # off-target tool.py edit before apply, so the docs task is neutralised to
    # a correct README change and passes; the other three wrong plans are still
    # caught by checkers. (Previously 0/4 with "docs-only request".)
    assert wrong.returncode == 1 and "Stable pass: 1/4" in wrong.stdout, wrong.stdout[
        -600:
    ]
    for needle in (
        "does not define sub()",
        "no working default",
    ):
        assert needle in wrong.stdout, needle
    print(
        "[PASS] wrong names and missing features are caught by checkers; off-target drift is neutralised by the target guard"
    )

    csv_line = next(l for l in golden.stdout.splitlines() if l.startswith("CSV:"))
    csv_path = Path(csv_line.split(":", 1)[1].strip())
    wrong_csv = next(l for l in wrong.stdout.splitlines() if l.startswith("CSV:")).split(":", 1)[1].strip()
    assert csv_path != Path(wrong_csv), "evaluation runs must not overwrite each other"
    assert csv_path.is_file() and csv_path.with_suffix(".md").is_file()
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == n and {
        "passed",
        "first_plan_ok",
        "elapsed_s",
        "prompt_tokens",
        "planner_calls",
        "verification",
    } <= set(rows[0])
    assert all(r["passed"] == "True" for r in rows)
    print(
        "[PASS] every task-run is recorded in CSV with timing/tokens/retry columns plus a Markdown summary"
    )

    # Fix-type requests get the project's failing output before planning; empty plans retry once.
    import json, tempfile
    from app.coding import WorkspaceCoworker
    from app.tools.workspace import WorkspaceManager
    from evals.coding.tasks import t04_setup

    ws = Path(tempfile.mkdtemp())
    t04_setup(ws)
    prompts = []

    class _Empty:
        def chat(self, messages, tools=None, format=None):
            prompts.append(messages[-1]["content"])
            return {
                "message": {"content": json.dumps({"files": [], "summary": "unsure"})}
            }

    out = WorkspaceCoworker(client=_Empty(), manager=WorkspaceManager(ws)).handle(
        "the test suite fails; fix the code in slugify.py so test_trim passes without changing the tests"
    )
    assert (
        len(prompts) == 2
        and "CURRENT VERIFICATION OUTPUT" in prompts[0]
        and "test_trim" in prompts[0]
    )
    assert (
        "contained no file changes" in prompts[1]
        and "did not change the workspace" in out
    )
    assert "PREVIOUS PLAN WAS INCOMPLETE" not in prompts[0]
    print(
        "[PASS] 'it fails' requests carry the real failing output; an empty plan is retried once with the reason"
    )

    # A plan whose JSON stops mid-string is retried once asking for a compact patch plan.
    from evals.coding.tasks import t09_setup

    ws9 = Path(tempfile.mkdtemp())
    t09_setup(ws9)
    calls = []

    class _Truncating:
        def chat(self, messages, tools=None, format=None, num_predict=None):
            calls.append((messages[-1]["content"], num_predict))
            if len(calls) == 1:
                return {
                    "message": {
                        "content": '{\n  "files": [\n    {\n      "path": "math.test.js",\n      "mode": "replace",\n      "content": "import test from'
                    }
                }
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "files": [
                                {
                                    "path": "math.js",
                                    "mode": "patch",
                                    "old_text": "  return a + b;\n}\n",
                                    "new_text": "  return a + b;\n}\n\nexport function clamp(v, lo, hi) {\n  return Math.min(Math.max(v, lo), hi);\n}\n",
                                }
                            ],
                            "summary": "clamp",
                        }
                    )
                }
            }

    out9 = WorkspaceCoworker(
        client=_Truncating(), manager=WorkspaceManager(ws9)
    ).handle(
        "add an exported clamp(value, min, max) function to math.js and a test for it in math.test.js"
    )
    assert 256 <= calls[0][1] <= WorkspaceCoworker.PLAN_NUM_PREDICT
    assert "cut off" in calls[1][0] and "mode=patch" in calls[1][0]
    assert "Updated:" in out9 and "export function clamp" in (
        ws9 / "math.js"
    ).read_text(encoding="utf-8"), (
        "truncated-plan retry did not survive verification; output was:\n" + out9
    )
    print(
        "[PASS] a truncated plan is a retryable gap (explicit num_predict, compact-patch retry), not an exception"
    )

    assert "EXCEPTION:" in Path("scripts/coding_eval.py").read_text(encoding="utf-8")
    assert "app={APP_VERSION}" in Path("scripts/coding_eval.py").read_text(
        encoding="utf-8"
    )
    from app.coding.explore import plan_gaps

    g = plan_gaps(
        "add a sub function to calc.py and a unittest for it",
        {
            "files": [
                {"path": "calc.py", "new_text": "def subtract(a,b): pass"},
                {"path": "test_calc.py", "new_text": "def test_subtract(): pass"},
            ]
        },
        set(),
    )
    assert any("EXACTLY that identifier" in x and "`sub`" in x for x in g), g
    print(
        "[PASS] eval surfaces application exceptions and prints the app version; name gaps are explicit"
    )

    listing = subprocess.run(
        [sys.executable, "-m", "scripts.coding_eval", "--list"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert listing.returncode == 0 and "py.edit_buried_function" in listing.stdout
    print("[PASS] --list shows tasks and which binaries optional tasks need")

    os.environ["RAZAAI_CODE_MODEL"] = "qwen2.5-coder:3b"
    import app.config as config

    importlib.reload(config)
    # The approved registry is authoritative; unknown tags are
    # rejected rather than silently switching the coder model.
    assert (
        config.CODE_MODEL == "qwen2.5-coder:3b"
        and not config.CODE_MODEL_OVERRIDE_REJECTED
        and config.OLLAMA_MODEL != config.CODE_MODEL
    )
    os.environ.pop("RAZAAI_CODE_MODEL")
    importlib.reload(config)
    # Assert config.CODE_MODEL == config.OLLAMA_MODEL
    agent_source = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "OllamaClient(model=CODE_MODEL) if self.code_model_active" in agent_source
    main_source = Path("app/main.py").read_text(encoding="utf-8")
    assert "_restore_conversation_model" in main_source and "warm_model(model=OLLAMA_MODEL" in main_source
    print(
        "[PASS] RAZAAI_CODE_MODEL selects a coder model for coding sessions and the conversation model is re-warmed on exit"
    )

    print("=" * 78)
    print("STEP 20.12.0 CODING EVALUATION HARNESS PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
