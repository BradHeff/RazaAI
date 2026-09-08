"""Terminal no-change self-improvement outcome."""

import tempfile
from pathlib import Path

from app.selfops.improvement import SelfImprovementManager


def main():
    print("=" * 76)
    print("RazaAI Step 20.5.8 No-Change Completion")
    print("=" * 76)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app").mkdir()
        (root / "scripts").mkdir()
        (root / "tests").mkdir()
        (root / "app/example.py").write_text("VALUE = 1\n", encoding="utf-8")

        manager = SelfImprovementManager(project_root=root)
        job = manager.start("Improve example behavior")
        completed = manager.complete_no_change(
            job["improvement_id"],
            reason="Inspected evidence already satisfies the requested behavior.",
            evidence=["app/example.py:1-1"],
        )

        assert completed["status"] == "not_required"
        assert completed["verified"] is False
        assert completed["changed_files"] == []
        assert "already satisfies" in completed["no_change_reason"]
        assert completed["no_change_evidence"] == ["app/example.py:1-1"]
        assert completed.get("completed_at")
        print("[PASS] evidence-backed no-op becomes terminal not_required")

        try:
            manager.promote(job["improvement_id"])
        except ValueError as exc:
            assert "Only a verified improvement candidate can be promoted" in str(exc)
        else:
            raise AssertionError("not_required job must never be promotable")
        print("[PASS] not_required jobs cannot be promoted")

    tool_source = Path("app/tools/improvement.py").read_text(encoding="utf-8")
    registry_source = Path("app/tools/registry.py").read_text(encoding="utf-8")
    orchestrator = Path("app/selfops/orchestrator.py").read_text(encoding="utf-8")
    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")

    assert "COMPLETE_SELF_IMPROVEMENT_NO_CHANGE_METADATA" in tool_source
    assert '"complete_self_improvement_no_change","selfops","sandbox_write",10,False' in tool_source.replace("\n", "")
    assert '"complete_self_improvement_no_change"' in registry_source
    assert '"complete_self_improvement_no_change"' in orchestrator
    assert 'status == "not_required"' in agent
    print("[PASS] no-change completion is Python-owned and hidden from model exposure")

    print()
    print("=" * 76)
    print("STEP 20.5.8 NO-CHANGE COMPLETION PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
