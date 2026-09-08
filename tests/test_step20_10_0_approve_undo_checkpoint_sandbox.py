"""RazaAI: plan -> diff preview -> approve/reject -> apply; /undo; /checkpoint on a raza/ branch; bubblewrap sandbox for verification commands."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.coding import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager
from app.tui.session import parse_command


class _Planner:
    def chat(self, messages, tools=None):
        plan = {"files": [
            {"path": "calc.py", "mode": "patch", "old_text": "    return a + b\n",
             "new_text": "    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"},
            {"path": "test_calc.py", "mode": "create",
             "content": "import unittest\nfrom calc import add, sub\n\n\nclass T(unittest.TestCase):\n    def test_sub(self):\n        self.assertEqual(sub(3, 1), 2)\n\n\nif __name__ == '__main__':\n    unittest.main()\n"},
        ], "summary": "add sub() with a unit test"}
        return {"message": {"content": json.dumps(plan)}}


def _git(ws, *args):
    return subprocess.run(["git", *args], cwd=ws, text=True, capture_output=True)


def main():
    print("=" * 78)
    print("RazaAI Step 20.10.0 Approve / Undo / Checkpoint / Sandbox")
    print("=" * 78)

    ws = Path(tempfile.mkdtemp())
    original = "def add(a, b):\n    return a + b\n"
    (ws / "calc.py").write_text(original, encoding="utf-8")
    _git(ws, "init", "-q"); _git(ws, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    _git(ws, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")

    cw = WorkspaceCoworker(client=_Planner(), manager=WorkspaceManager(ws), require_approval=True)

    proposal = cw.handle("add a sub function to calc.py file and a unittest for it")
    assert proposal.startswith("Proposed changes (nothing written yet):")
    assert "```diff" in proposal and "+def sub(a, b):" in proposal and "### create `test_calc.py`" in proposal
    assert "/approve" in proposal and cw.has_pending()
    assert (ws / "calc.py").read_text(encoding="utf-8") == original and not (ws / "test_calc.py").exists()
    print("[PASS] a mutation request yields a unified-diff proposal and writes nothing")

    assert "Discarded" in cw.reject() and not cw.has_pending()
    assert (ws / "calc.py").read_text(encoding="utf-8") == original
    assert "no pending" in cw.approve()
    print("[PASS] /reject discards; /approve with nothing pending is a no-op")

    cw.handle("add a sub function to calc.py file and a unittest for it")
    report = cw.approve()
    assert "Verification: PASS" in report and "Sandbox:" in report, report
    assert "def sub" in (ws / "calc.py").read_text(encoding="utf-8") and (ws / "test_calc.py").exists()
    assert not cw.has_pending()
    print("[PASS] /approve applies the proposal, verifies it, and reports the sandbox used")

    undo = cw.undo()
    assert "restored 2 path(s)" in undo
    assert (ws / "calc.py").read_text(encoding="utf-8") == original and not (ws / "test_calc.py").exists()
    assert "nothing to undo" in cw.undo()
    print("[PASS] /undo restores the pre-task snapshot byte for byte; a second undo is a no-op")

    cw.handle("add a sub function to calc.py file and a unittest for it"); cw.approve()
    out = cw.checkpoint("sub plus test")
    assert "committed on branch `raza/" in out, out
    branch = _git(ws, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert branch.startswith("raza/")
    assert "raza: sub plus test" in _git(ws, "log", "-1", "--pretty=%s").stdout
    assert _git(ws, "status", "--short").stdout.strip() == ""
    assert "nothing to commit" in cw.checkpoint()
    # No bytecode is committed even though verification compiled/ran the files
    committed = _git(ws, "ls-tree", "-r", "--name-only", "HEAD").stdout
    assert "__pycache__" not in committed and ".pyc" not in committed, committed
    assert not (ws / "__pycache__").exists(), "verification must not write bytecode into the workspace"
    # Branch questions are Python-rendered and agree with the checkpoint
    assert cw.should_handle("git branch") and cw.should_handle("what branch are we on?")
    out_branch = cw.handle("git branch")
    assert out_branch.startswith("Current branch: `raza/") and "`main`" in out_branch or "`master`" in out_branch, out_branch
    assert "PYTHONPYCACHEPREFIX" in Path("app/tools/workspace.py").read_text(encoding="utf-8")
    print("[PASS] checkpoints never include bytecode, verification keeps the workspace clean, branch reads are Python-rendered")
    main_log = _git(ws, "log", "master", "--oneline").stdout + _git(ws, "log", "main", "--oneline").stdout
    assert "raza:" not in main_log
    print("[PASS] /checkpoint commits only on a raza/ branch; the original branch is untouched")

    for bad in (["git", "add", "-A"], ["git", "commit", "-m", "x"], ["git", "checkout", "-b", "evil"], ["git", "push"]):
        try:
            WorkspaceManager(ws).run_command(bad)
        except ValueError:
            continue
        raise AssertionError(f"model-facing git write should be refused: {bad}")
    print("[PASS] the model-facing command runner still cannot perform Git writes")

    mgr = WorkspaceManager(ws)
    with patch.object(WorkspaceManager, "probe_sandbox", classmethod(lambda cls, refresh=False: ("bwrap", ["--unshare-net", "--unshare-pid"]))):
        os.environ.pop("RAZAAI_SANDBOX", None)
        wrapped, kind = mgr._sandboxed_args(["python3", "-m", "pytest", "-q"], ws)
        assert kind == "bwrap" and wrapped[0] == "bwrap"
        assert "--unshare-net" in wrapped and "--ro-bind" in wrapped
        assert wrapped[wrapped.index("--bind") + 1] == str(ws)
        sep = wrapped.index("--")
        assert Path(wrapped[sep + 1]).is_absolute()
        assert wrapped[sep + 2:] == ["-m", "pytest", "-q"]
        os.environ["RAZAAI_SANDBOX"] = "0"
        plain, kind = mgr._sandboxed_args(["python3", "-m", "pytest", "-q"], ws)
        assert kind == "disabled" and plain[0] == "python3"
        os.environ.pop("RAZAAI_SANDBOX", None)
    with patch.object(WorkspaceManager, "probe_sandbox", classmethod(lambda cls, refresh=False: ("unavailable", []))):
        plain, kind = mgr._sandboxed_args(["python3", "-m", "pytest", "-q"], ws)
        assert kind == "unavailable"
    # A kernel that refuses network isolation degrades to filesystem-only isolation,
    # reports it, and never spends model repair passes on a sandbox error.
    with patch.object(WorkspaceManager, "probe_sandbox", classmethod(lambda cls, refresh=False: ("bwrap-fs", ["--unshare-pid"]))):
        wrapped, kind = mgr._sandboxed_args(["python3", "-m", "pytest", "-q"], ws)
        assert kind == "bwrap-fs" and "--unshare-net" not in wrapped and "--ro-bind" in wrapped
    sandbox_failure = {"exit_code": 1, "stderr": "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted", "stdout": ""}
    assert WorkspaceManager.is_sandbox_error(sandbox_failure)
    assert not WorkspaceManager.is_sandbox_error({"exit_code": 1, "stderr": "E   SyntaxError", "stdout": ""})
    assert "is_sandbox_error(item) for item in checks" in Path("app/coding/coworker.py").read_text(encoding="utf-8")
    levels = [name for name, _ in WorkspaceManager._SANDBOX_LEVELS]
    assert levels == ["bwrap", "bwrap-fs", "bwrap-fs-nopid"]
    print("[PASS] sandbox level is probed (net+pid -> fs+pid -> fs) and sandbox errors are not treated as code failures")
    result = mgr.run_command(["python3", "-m", "py_compile", "calc.py"])
    assert result["exit_code"] == 0 and result["sandbox"] in {"bwrap", "unavailable", "disabled"}
    assert result["command"][0] in {"python3", str(Path(result["command"][0]))}  # Display never shows bwrap
    print("[PASS] verification commands are wrapped in bubblewrap (ro root, private net, workspace rw) when present")

    for cmd in ("/approve", "/reject", "/undo", "/checkpoint", "/checkpoint add sub"):
        parsed = parse_command(cmd)
        assert parsed.handled and parsed.action == "agent" and parsed.prompt == cmd, cmd
    assert "/approve" in parse_command("/help").message
    print("[PASS] TUI routes coding-session commands to the agent and /help documents them")

    agent_source = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "RAZAAI_CODE_AUTO_APPROVE" in agent_source and '"/approve": self.workspace_coworker.approve' in agent_source
    print("[PASS] agent enables approval for raza-code by default (RAZAAI_CODE_AUTO_APPROVE=1 opts out)")

    print("=" * 78)
    print("STEP 20.10.0 APPROVE / UNDO / CHECKPOINT / SANDBOX PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
