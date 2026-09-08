"""RazaAI project verification and Git evidence."""

import subprocess
import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager


class NoModelClient:
    def chat(self, messages, tools=None):
        raise AssertionError("deterministic status/test commands must not call the model")


def _git(root, *args):
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.0 Project Checks + Git Evidence")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n",
            encoding="utf-8",
        )
        (root / "test_calc.py").write_text(
            "import unittest\n"
            "from calc import add\n\n"
            "class CalcTests(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n",
            encoding="utf-8",
        )

        coworker = WorkspaceCoworker(
            client=NoModelClient(),
            manager=WorkspaceManager(root),
        )

        checks = coworker.handle("run tests")
        assert "python3 -m unittest discover" in checks
        assert "Overall: **PASS**" in checks
        print("[PASS] project-aware test detection uses standard-library unittest when appropriate")

        _git(root, "init")
        _git(root, "config", "user.email", "raza@example.invalid")
        _git(root, "config", "user.name", "RazaAI Test")
        _git(root, "add", "calc.py", "test_calc.py")
        _git(root, "commit", "-m", "baseline")
        (root / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n\n"
            "def subtract(a, b):\n    return a - b\n",
            encoding="utf-8",
        )

        status = coworker.handle("git status")
        diff = coworker.handle("git diff")
        assert "calc.py" in status
        assert "subtract" in diff
        print("[PASS] git status and diff are grounded directly in workspace Git evidence")

    manager_source = Path("app/tools/workspace.py").read_text(encoding="utf-8")
    assert "except FileNotFoundError" in manager_source
    assert "except subprocess.TimeoutExpired" in manager_source
    assert "shell=False" in manager_source
    print("[PASS] command runner reports missing/timeout tools without gaining shell authority")

    print()
    print("=" * 78)
    print("STEP 20.8.0 PROJECT CHECKS + GIT EVIDENCE PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
