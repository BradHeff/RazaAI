"""Crash-safe coding transaction journal and restart recovery."""

import json
import os
import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.tools.workspace import WorkspaceManager


class _Planner:
    def chat(self, messages, tools=None, **kwargs):
        plan = {
            "files": [
                {
                    "path": "calc.py",
                    "mode": "patch",
                    "old_text": "    return a + b\n",
                    "new_text": "    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
                }
            ],
            "summary": "add sub",
        }
        return {"message": {"content": json.dumps(plan)}}


class _CrashAfterPatch(WorkspaceManager):
    def patch_file(self, path, old_text, new_text):
        result = super().patch_file(path, old_text, new_text)
        raise SystemExit("simulated power loss after durable workspace write")


class _CrashDuringUndo(WorkspaceManager):
    def write_file(self, path, content, overwrite=False):
        result = super().write_file(path, content, overwrite=overwrite)
        raise SystemExit("simulated power loss during undo")


def _workspace():
    ws = Path(tempfile.mkdtemp())
    (ws / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    return ws


def main():
    print("=" * 78)
    print("RazaAI Step 20.14.1 Transaction Durability")
    print("=" * 78)
    previous_state = os.environ.get("RAZAAI_STATE_DIR")
    state = Path(tempfile.mkdtemp())
    os.environ["RAZAAI_STATE_DIR"] = str(state)
    try:
        # Pending approval must survive the process that created it.
        ws = _workspace()
        cw1 = WorkspaceCoworker(client=_Planner(), manager=WorkspaceManager(ws), require_approval=True)
        proposal = cw1.handle("add a sub function to calc.py")
        assert proposal.startswith("Proposed changes") and cw1.has_pending()
        txid = cw1.pending["txid"]
        cw2 = WorkspaceCoworker(client=_Planner(), manager=WorkspaceManager(ws), require_approval=True)
        assert cw2.has_pending() and cw2.pending["txid"] == txid
        assert "Verification: PASS" in cw2.approve()
        assert "def sub" in (ws / "calc.py").read_text(encoding="utf-8")
        print("[PASS] pending proposal survives restart and can be approved safely")

        # /undo authority must also survive restart after successful verification.
        cw3 = WorkspaceCoworker(client=_Planner(), manager=WorkspaceManager(ws), require_approval=True)
        assert cw3.last_applied and cw3.last_applied["txid"] == txid
        undo = cw3.undo()
        assert "restored 1 path(s)" in undo
        assert "def sub" not in (ws / "calc.py").read_text(encoding="utf-8")
        cw4 = WorkspaceCoworker(client=_Planner(), manager=WorkspaceManager(ws), require_approval=True)
        assert cw4.last_applied is None
        print("[PASS] verified transaction keeps durable /undo authority across restart")

        # Simulate abrupt termination after the file write. BaseException escapes the
        # current process, leaving the journal in 'applying'; the next process must
        # restore the exact pre-task snapshot before accepting more coding work.
        ws2 = _workspace()
        original = (ws2 / "calc.py").read_text(encoding="utf-8")
        crashing = WorkspaceCoworker(client=_Planner(), manager=_CrashAfterPatch(ws2), require_approval=True)
        crashing.handle("add a sub function to calc.py")
        try:
            crashing.approve()
        except SystemExit:
            pass
        else:
            raise AssertionError("simulated crash did not interrupt apply")
        assert "def sub" in (ws2 / "calc.py").read_text(encoding="utf-8")

        recovered = WorkspaceCoworker(client=_Planner(), manager=WorkspaceManager(ws2), require_approval=True)
        assert (ws2 / "calc.py").read_text(encoding="utf-8") == original
        assert recovered.recovery_status() and "Recovered interrupted coding transaction" in recovered.recovery_status()
        latest = recovered.journal.latest()
        assert latest and latest["state"] == "rolled_back" and latest.get("recovery") is True
        print("[PASS] interrupted apply is automatically rolled back from durable snapshot on restart")

        ws_undo = _workspace()
        normal = WorkspaceCoworker(client=_Planner(), manager=WorkspaceManager(ws_undo), require_approval=True)
        normal.handle("add a sub function to calc.py")
        assert "Verification: PASS" in normal.approve()
        crashing_undo = WorkspaceCoworker(client=_Planner(), manager=_CrashDuringUndo(ws_undo), require_approval=True)
        try:
            crashing_undo.undo()
        except SystemExit:
            pass
        else:
            raise AssertionError("simulated crash did not interrupt undo")
        recovered_undo = WorkspaceCoworker(client=_Planner(), manager=WorkspaceManager(ws_undo), require_approval=True)
        assert "def sub" not in (ws_undo / "calc.py").read_text(encoding="utf-8")
        assert recovered_undo.journal.latest()["state"] == "undone"
        assert recovered_undo.last_applied is None
        print("[PASS] interrupted /undo resumes safely after restart and does not re-arm old undo authority")

        # Snapshot payload integrity is verified before recovery/undo is trusted.
        ws3 = _workspace()
        cw5 = WorkspaceCoworker(client=_Planner(), manager=WorkspaceManager(ws3), require_approval=True)
        cw5.handle("add a sub function to calc.py")
        assert "Verification: PASS" in cw5.approve()
        txid3 = cw5.last_applied["txid"]
        manifest = cw5.journal._read_json(cw5.journal._tx_dir(txid3) / "snapshot.json")
        record = manifest["files"]["calc.py"]
        payload = cw5.journal._tx_dir(txid3) / "snapshots" / record["file"]
        payload.write_text("tampered", encoding="utf-8")
        try:
            cw5.journal.load_snapshot(txid3)
        except ValueError as exc:
            assert "integrity" in str(exc).casefold()
        else:
            raise AssertionError("tampered durable snapshot was accepted")
        print("[PASS] durable snapshots are hash-checked before rollback authority is used")
    finally:
        if previous_state is None:
            os.environ.pop("RAZAAI_STATE_DIR", None)
        else:
            os.environ["RAZAAI_STATE_DIR"] = previous_state

    print("=" * 78)
    print("STEP 20.14.1 TRANSACTION DURABILITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
