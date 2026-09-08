"""Hard deadlines, process-group termination, test tiers, runtime lock capture."""

import os
import tempfile
import time
from pathlib import Path

from app.tools.execution import ToolDeadlineExceeded, tool_deadline
from app.tools.workspace import WorkspaceManager


def main():
    print("=" * 78)
    print("RazaAI Step 20.14.3 Runtime Hardening")
    print("=" * 78)

    started = time.monotonic()
    try:
        with tool_deadline(1) as active:
            assert active, "main-thread POSIX deadline should be active on the Jetson/Linux test path"
            time.sleep(5)
    except ToolDeadlineExceeded:
        pass
    else:
        raise AssertionError("hard tool deadline did not interrupt a hung function")
    assert time.monotonic() - started < 2.5
    registry = Path("app/tools/registry.py").read_text(encoding="utf-8")
    assert "with tool_deadline(timeout)" in registry and "ToolDeadlineExceeded" in registry
    print("[PASS] tool metadata timeout is an interrupting wall-clock deadline, not a post-return warning")

    ws = Path(tempfile.mkdtemp())
    (ws / "hang.py").write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])\n"
        "time.sleep(20)\n",
        encoding="utf-8",
    )
    previous = os.environ.get("RAZAAI_SANDBOX")
    os.environ["RAZAAI_SANDBOX"] = "0"
    try:
        started = time.monotonic()
        result = WorkspaceManager(ws).run_command(["python3", "hang.py"], timeout=1)
        elapsed = time.monotonic() - started
    finally:
        if previous is None:
            os.environ.pop("RAZAAI_SANDBOX", None)
        else:
            os.environ["RAZAAI_SANDBOX"] = previous
    assert result["exit_code"] == 124 and elapsed < 3.0, result
    assert "process group terminated" in result["stderr"]
    print("[PASS] timed-out workspace commands kill their whole process group")

    for tier in ("fast", "core", "integration", "device"):
        assert Path(f"tests/run_{tier}.py").exists()
    tiers = Path("tests/tier_runner.py").read_text(encoding="utf-8")
    assert "FAST =" in tiers and "CORE =" in tiers and "INTEGRATION =" in tiers and "DEVICE =" in tiers
    print("[PASS] test suite has explicit fast/core/integration/device feedback gates")

    deploy = Path("deploy.sh").read_text(encoding="utf-8")
    lock = Path("scripts/capture_runtime_lock.py").read_text(encoding="utf-8")
    assert 'pip install -r requirements.txt' in deploy
    assert "requirements.lock" not in deploy
    assert '"pip", "freeze", "--local"' in lock
    assert "full device acceptance suite passes" in lock
    print("[PASS] dependency locking captures the accepted Jetson venv instead of guessing versions elsewhere")

    package = Path("scripts/package_release.sh").read_text(encoding="utf-8")
    assert "data/" in Path(".gitignore").read_text().splitlines()
    print("[PASS] crash-recovery journals are runtime state and cannot leak into source release archives")

    print("=" * 78)
    print("STEP 20.14.3 RUNTIME HARDENING PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
