"""RazaAI:  repair-pass truncation guard and failed-verification rollback."""

import json
import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager


def _big_source(n=400):
    return "".join(f"def keep_{i}():\n    return {i}\n\n" for i in range(n))


# Syntax errors are caught before a proposal, so the repair path is
# exercised with a SEMANTIC break (parses, fails the unit test) instead.
_TEST_BIG = "import unittest\nfrom big import keep_0\n\n\nclass T(unittest.TestCase):\n    def test_keep_0(self):\n        self.assertEqual(keep_0(), 0)\n"


class _BreakThenReplaceClient:
    """Planner breaks keep_0 semantically; repair returns a full replacement of the clipped view."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            plan = {"files": [{"path": "big.py", "mode": "patch",
                               "old_text": "def keep_0():\n    return 0\n", "new_text": "def keep_0():\n    return 1\n"}],
                    "summary": "introduce error"}
        else:
            seen = messages[1]["content"].split("FILE: big.py\n", 1)[1]
            seen = seen.split("\n", 1)[1]  # Drop CLIPPED line
            plan = {"files": [{"path": "big.py", "mode": "replace",
                               "content": seen.replace("    return 1\n", "    return 0\n", 1)}],
                    "summary": "repair"}
        return {"message": {"content": json.dumps(plan)}}


class _BreakThenPatchClient(_BreakThenReplaceClient):
    """Same failure but a correct patch-mode repair on the clipped file."""

    def chat(self, messages, tools=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            plan = {"files": [{"path": "big.py", "mode": "patch",
                               "old_text": "def keep_0():\n    return 0\n", "new_text": "def keep_0():\n    return 1\n"}],
                    "summary": "introduce error"}
            return {"message": {"content": json.dumps(plan)}}
        plan = {"files": [{"path": "big.py", "mode": "patch",
                           "old_text": "def keep_0():\n    return 1\n", "new_text": "def keep_0():\n    return 0\n"}],
                "summary": "repair"}
        return {"message": {"content": json.dumps(plan)}}


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.1 Repair Truncation Guard + Rollback")
    print("=" * 78)


    # Workspace is restored, so no truncation reaches disk.
    ws = Path(tempfile.mkdtemp())
    src = _big_source()
    (ws / "big.py").write_text(src, encoding="utf-8")
    (ws / "test_big.py").write_text(_TEST_BIG, encoding="utf-8")
    assert len(src) > WorkspaceCoworker.REPAIR_READ_CHARS
    cw = WorkspaceCoworker(client=_BreakThenReplaceClient(), manager=WorkspaceManager(ws))
    result = cw.handle("change keep_0 in big.py file")
    after = (ws / "big.py").read_text(encoding="utf-8")
    assert after == src, "file must be byte-identical after rollback"
    assert "def keep_399" in after
    assert "restored" in result.casefold()
    assert "Verification: PASS" not in result
    assert "full replacement refused for clipped file" in result
    print("[PASS] clipped-file replacement in repair is refused and workspace restored")


    ws2 = Path(tempfile.mkdtemp())
    (ws2 / "big.py").write_text(src, encoding="utf-8")
    (ws2 / "test_big.py").write_text(_TEST_BIG, encoding="utf-8")
    cw2 = WorkspaceCoworker(client=_BreakThenPatchClient(), manager=WorkspaceManager(ws2))
    result2 = cw2.handle("change keep_0 in big.py file")
    after2 = (ws2 / "big.py").read_text(encoding="utf-8")
    assert after2 == src
    assert "Verification: PASS" in result2
    assert "Automatic repair passes: 1" in result2
    print("[PASS] patch-mode repair preserves the full file and verification passes")


    ws3 = Path(tempfile.mkdtemp())
    (ws3 / "mod.py").write_text(src, encoding="utf-8")

    class _Shrinker:
        def chat(self, messages, tools=None, **kwargs):
            return {"message": {"content": json.dumps({
                "files": [{"path": "mod.py", "mode": "replace", "content": "def keep_0():\n    return 0\n"}],
                "summary": "rewrite"})}}

    cw3 = WorkspaceCoworker(client=_Shrinker(), manager=WorkspaceManager(ws3))
    result3 = cw3.handle("refactor mod.py file")
    assert (ws3 / "mod.py").read_text(encoding="utf-8") == src
    assert "remove more than 40%" in result3
    print("[PASS] planner replacement that would shrink a file by >40% is refused")


    assert "not claiming the task is complete" in result
    print("[PASS] failed-verification report never claims completion")

    print("=" * 78)
    print("STEP 20.8.1 REPAIR TRUNCATION GUARD + ROLLBACK PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
