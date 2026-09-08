"""RazaAI operational self-improvement feedback loop."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from app.selfops.feedback import ImprovementFeedbackStore
from app.selfops.discovery import ImprovementDiscoveryEngine


def main():
    print("=" * 78)
    print("RazaAI Step 20.7.0 Operational Improvement Feedback Loop")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app/playbooks").mkdir(parents=True)
        (root / "data/self_audits").mkdir(parents=True)
        (root / "output/model-evals").mkdir(parents=True)
        (root / "app/playbooks/technical_guidance.py").write_text(
            'NPS_GUIDANCE = "evidence-first"\n', encoding="utf-8"
        )

        store = ImprovementFeedbackStore(root)
        first = store.record(
            "user_correction",
            topic="NPS EAP WiFi troubleshooting",
            domain="networking",
            summary="User corrected the previous NPS answer.",
            source="conversation",
            severity="medium",
            file="app/playbooks/technical_guidance.py",
        )
        assert first["kind"] == "user_correction"

        engine = ImprovementDiscoveryEngine(root)
        report = engine.discover(limit=5)
        assert report["opportunities"] == []
        print("[PASS] one conversational signal is stored but cannot trigger auto improvement")

        store.record(
            "user_correction",
            topic="NPS EAP WiFi troubleshooting",
            domain="networking",
            summary="A second correction confirms a repeated weakness.",
            source="conversation",
            severity="medium",
            file="app/playbooks/technical_guidance.py",
        )
        report = engine.discover(limit=5)
        signal_items = [x for x in report["opportunities"] if x["source"] == "feedback_signal"]
        assert signal_items
        assert signal_items[0]["auto_eligible"] is True
        assert "2 times" in signal_items[0]["reason"]
        print("[PASS] repeated related corrections become evidence-backed opportunities")

        correction = store.observe_user_followup(
            "No, it is already on VLAN 80",
            previous_user="how to fix NPS EAP WiFi troubleshooting?",
            previous_assistant="Change the WLAN to VLAN 80.",
            domain="networking",
            sensitive=False,
        )
        assert correction and correction["kind"] == "user_correction"
        positive = store.observe_user_followup(
            "that worked, it is working now",
            previous_user="check the NPS policy",
            previous_assistant="Check the reason code and matching Network Policy.",
            domain="networking",
            sensitive=False,
        )
        assert positive and positive["kind"] == "successful_resolution"
        print("[PASS] user corrections and explicit successful outcomes are persisted distinctly")

        promoted_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        store.record_promotion({
            "improvement_id": "IMPROVE-20260822-010101-000001",
            "promoted_at": promoted_at,
            "goal": "NPS EAP WiFi troubleshooting",
            "changed_files": ["app/playbooks/technical_guidance.py"],
            "risk": "medium",
        })
        history = store.history(limit=10)
        assert history
        assert history[0]["improvement_id"] == "IMPROVE-20260822-010101-000001"
        assert history[0]["successful_outcomes_after"] >= 1
        print("[PASS] promoted improvements are measured against later issue/success signals")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    evaluation = Path("app/evaluation/capabilities.py").read_text(encoding="utf-8")
    improvement = Path("app/selfops/improvement.py").read_text(encoding="utf-8")
    assert "observe_user_followup" in agent
    assert '"context_overflow"' in agent
    assert '"document_failure"' in agent
    assert '"web_grounding_rejection"' in agent
    assert '"capability_failure"' in evaluation
    assert "record_promotion" in improvement
    print("[PASS] runtime, capability and promotion signal producers are wired")

    print()
    print("=" * 78)
    print("STEP 20.7.0 OPERATIONAL FEEDBACK LOOP PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
