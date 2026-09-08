"""Project verification executes in a disposable workspace copy."""

import json
import os
import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager


class _Planner:
    def chat(self, messages, tools=None, **kwargs):
        plan = {
            "files": [{
                "path": "calc.py", "mode": "patch",
                "old_text": "    return a + b\n",
                "new_text": "    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
            }],
            "summary": "add sub",
        }
        return {"message": {"content": json.dumps(plan)}}


def _make_workspace():
    ws = Path(tempfile.mkdtemp())
    (ws / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    # Import-time write proves whether verification is running in the real tree.
    (ws / "test_side_effect.py").write_text(
        "from pathlib import Path\n"
        "import unittest\n\n"
        "Path('verification_side_effect.txt').write_text('created by test', encoding='utf-8')\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        from calc import add\n"
        "        self.assertEqual(add(2, 3), 5)\n",
        encoding="utf-8",
    )
    return ws


def main():
    print("=" * 78)
    print("RazaAI Step 20.14.2 Verification Isolation")
    print("=" * 78)
    previous_state = os.environ.get("RAZAAI_STATE_DIR")
    os.environ["RAZAAI_STATE_DIR"] = tempfile.mkdtemp()
    try:
        ws = _make_workspace()
        cw = WorkspaceCoworker(client=_Planner(), manager=WorkspaceManager(ws), require_approval=True)
        cw.handle("add a sub function to calc.py")
        report = cw.approve()
        assert "Verification: PASS" in report, report
        assert not (ws / "verification_side_effect.txt").exists(), (
            "project test mutated the live workspace during automatic verification"
        )
        assert "def sub" in (ws / "calc.py").read_text(encoding="utf-8")
        print("[PASS] automatic post-write verification cannot leave test/build side effects in live source")

        # Explicit 'run tests' goes through the same isolation path.
        report2 = cw.run_project_checks()
        assert "Overall: **PASS**" in report2, report2
        assert not (ws / "verification_side_effect.txt").exists()
        print("[PASS] user-requested project checks also execute in a disposable workspace")

        manager = WorkspaceManager(ws)
        with manager.verification_workspace() as isolated:
            assert isolated.root != manager.root
            assert (isolated.root / "calc.py").read_text(encoding="utf-8") == (ws / "calc.py").read_text(encoding="utf-8")
            (isolated.root / "only-in-verification.txt").write_text("temp", encoding="utf-8")
            isolated_root = isolated.root
        assert not isolated_root.exists()
        assert not (ws / "only-in-verification.txt").exists()
        print("[PASS] verification copies are source-equivalent, disposable, and cleaned after execution")

        source = Path("app/coding/coworker.py").read_text(encoding="utf-8")
        assert "Fail closed" in source and "verification_workspace" in source
        print("[PASS] isolation failure cannot silently fall back to executing project code in the live workspace")
    finally:
        if previous_state is None:
            os.environ.pop("RAZAAI_STATE_DIR", None)
        else:
            os.environ["RAZAAI_STATE_DIR"] = previous_state

    print("=" * 78)
    print("STEP 20.14.2 VERIFICATION ISOLATION PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
