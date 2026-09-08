"""RazaAI:  verification runs with the project's own interpreter/tools."""

import os
import stat
import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager


def _fake_venv(root, marker="VENV-PY"):
    """A fake .venv whose python just echoes a marker and its argv."""
    bin_dir = root / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    py = bin_dir / "python3"
    py.write_text(
        "#!/bin/sh\n"
        f'echo "{marker} $*"\n'
        'echo "VIRTUAL_ENV=$VIRTUAL_ENV"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    py.chmod(py.stat().st_mode | stat.S_IXUSR)
    return py


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.5 Project Interpreter Authority")
    print("=" * 78)

    # 1. No venv: system interpreter, reported honestly.
    ws = Path(tempfile.mkdtemp())
    (ws / "a.py").write_text("x = 1\n", encoding="utf-8")
    m = WorkspaceManager(ws)
    info = m.project_interpreters()
    assert info["python"] is None and info["python_source"] == "system"
    out = m.run_command(["python3", "-m", "py_compile", "a.py"])
    assert out["exit_code"] == 0
    print("[PASS] projects without a venv use the launching interpreter")

    # 2. With .venv: python3/pytest are routed through it and VIRTUAL_ENV/PATH are set.
    ws2 = Path(tempfile.mkdtemp())
    (ws2 / "a.py").write_text("x = 1\n", encoding="utf-8")
    py = _fake_venv(ws2)
    m2 = WorkspaceManager(ws2)
    info2 = m2.project_interpreters()
    assert info2["python"] == str(py) and info2["python_source"] == ".venv"

    out2 = m2.run_command(["python3", "-m", "py_compile", "a.py"])
    assert out2["exit_code"] == 0, out2
    assert "VENV-PY -m py_compile" in out2["stdout"]
    assert f"VIRTUAL_ENV={ws2 / '.venv'}" in out2["stdout"]
    # The reported command still shows the validated, project-local executable.
    assert out2["command"][0] == str(py)
    print("[PASS] python3 is routed through the project's .venv")

    out3 = m2.run_command(["pytest", "-q"])
    assert "VENV-PY -m pytest -q" in out3["stdout"], out3
    print("[PASS] bare pytest runs as the venv's python -m pytest")

    # 3. Policy is unchanged: a venv does not widen what may be executed.
    for bad in (["python3", "-c", "print(1)"], ["bash", "-c", "true"], [str(py), "a.py"]):
        try:
            m2.run_command(bad)
        except ValueError:
            continue
        raise AssertionError(f"should have been rejected: {bad}")
    print("[PASS] interpreter substitution happens after validation, not instead of it")


    cw = WorkspaceCoworker(client=None, manager=m2)
    profile = cw._project_profile()
    assert profile["python_interpreter"] == ".venv"
    desc = cw.describe_workspace()
    assert "Python interpreter: .venv" in desc
    print("[PASS] workspace description states which interpreter verification uses")


    ws3 = Path(tempfile.mkdtemp())
    (ws3 / "node_modules" / ".bin").mkdir(parents=True)
    (ws3 / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    assert WorkspaceManager(ws3).project_interpreters()["node_bin"] == str(ws3 / "node_modules" / ".bin")
    print("[PASS] node projects expose node_modules/.bin to verification commands")

    print("=" * 78)
    print("STEP 20.8.5 PROJECT INTERPRETER AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
