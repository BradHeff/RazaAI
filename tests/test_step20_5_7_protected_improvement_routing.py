"""Protected-file-safe self-improvement routing."""

import tempfile
from pathlib import Path

from app.selfops.repair import SelfRepairManager
from app.selfops.improvement import SelfImprovementManager


def main():
    print("=" * 76)
    print("RazaAI Step 20.5.7 Protected Improvement Routing")
    print("=" * 76)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app/agent").mkdir(parents=True)
        (root / "app/playbooks").mkdir(parents=True)
        (root / "tests").mkdir(parents=True)

        (root / "app/agent/edge_router.py").write_text(
            'NPS = "NPS EAP WiFi troubleshooting VLAN RADIUS"\n' * 8,
            encoding="utf-8",
        )
        (root / "app/playbooks/technical_guidance.py").write_text(
            'NPS_GUIDANCE = "NPS EAP WiFi troubleshooting RADIUS evidence"\n' * 4,
            encoding="utf-8",
        )

        repair = SelfRepairManager(project_root=root)
        result = repair.investigate(
            "NPS EAP WiFi troubleshooting",
            max_files=3,
            context_lines=40,
        )

        files = [item["file"] for item in result["results"]]
        assert "app/agent/edge_router.py" not in files
        assert "app/playbooks/technical_guidance.py" in files
        assert "app/agent/edge_router.py" in result["skipped_protected"]
        print("[PASS] investigation skips protected authority and selects editable guidance")

        manager = SelfImprovementManager(project_root=root)
        assert manager.classify_risk("app/agent/edge_router.py") == "protected"
        assert manager.classify_risk("app/playbooks/technical_guidance.py") == "medium"
        print("[PASS] authority remains protected while playbook guidance is improvable")

    guidance = Path("app/playbooks/technical_guidance.py").read_text(encoding="utf-8")
    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    router = Path("app/agent/edge_router.py").read_text(encoding="utf-8")

    assert "NPS_EAP_ENTRY_RESPONSE" in guidance
    assert "NPS_EAP_GUIDANCE" in guidance
    assert "VOICE_IPSEC_GUIDANCE" in guidance
    assert "return networking_reasoning_guidance(text)" in agent
    assert "response=NPS_EAP_ENTRY_RESPONSE" in router
    print("[PASS] technical content is centralized in the editable playbook layer")

    print()
    print("=" * 76)
    print("STEP 20.5.7 PROTECTED IMPROVEMENT ROUTING PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
