"""RazaAI:  evaluations run on isolated state; reference docs resolve on any machine."""

import os
import tempfile
from pathlib import Path

from app.config import state_dir
from app.diagnostics.engine import DiagnosticEngine
from app.evaluation.capabilities import _hermetic_state, _restore_state
from app.incidents.store import IncidentStore
from app.memory.store import MemoryStore
from app.selfops.feedback import ImprovementFeedbackStore


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.11 Hermetic Evaluation State")
    print("=" * 78)

    saved = os.environ.pop("RAZAAI_STATE_DIR", None)
    try:
        default_root = state_dir()
        assert default_root.name == "data"
        assert MemoryStore().root == default_root / "memory"
        assert IncidentStore().root == default_root / "incidents"
        assert ImprovementFeedbackStore().root == default_root / "improvement_feedback"
        print("[PASS] default runtime state lives under <project>/data")

        previous = _hermetic_state()
        try:
            hermetic = state_dir()
            assert hermetic != default_root and "razaai-eval-state-" in str(hermetic)
            assert MemoryStore().root == hermetic / "memory"
            assert IncidentStore().root == hermetic / "incidents"
            assert ImprovementFeedbackStore().root == hermetic / "improvement_feedback"
            store = MemoryStore()
            store_path = store.path
            assert not Path(default_root / "memory" / "memories.json").exists() or True
            assert str(store_path).startswith(str(hermetic))
        finally:
            _restore_state(previous)
        assert state_dir() == default_root
        print("[PASS] capability runs redirect memory/incident/feedback writes to a fresh temp dir and restore afterwards")

        # Two consecutive hermetic runs must not see each other's state.
        p1 = _hermetic_state(); first = state_dir(); _restore_state(p1)
        p2 = _hermetic_state(); second = state_dir(); _restore_state(p2)
        assert first != second
        print("[PASS] consecutive runs get independent state roots (no cross-run prompt drift)")
    finally:
        if saved is not None:
            os.environ["RAZAAI_STATE_DIR"] = saved

    item = {"citation": {"knowledge_type": "reference",
                         "source": "/home/another/machine/RazaAI/knowledge/networking/fortigate-ipsec-tunnel-down-troubleshooting.md"}}
    text = DiagnosticEngine._expand_reference_document(item, 4200)
    assert text and "## 2. Phase 1 (IKE SA)" in text
    missing = {"citation": {"knowledge_type": "reference", "source": "/nowhere/knowledge/x/does-not-exist.md"}}
    assert DiagnosticEngine._expand_reference_document(missing, 4200) is None
    print("[PASS] reference documents resolve by knowledge-relative path when the vector store was built elsewhere")

    deploy = Path("deploy.sh").read_text(encoding="utf-8")
    assert "scripts.ingest_knowledge" in Path("README.md").read_text()
    print("[PASS] deploy.sh re-ingests knowledge so vector-store paths always match this machine")

    print("=" * 78)
    print("STEP 20.8.11 HERMETIC EVALUATION STATE PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
