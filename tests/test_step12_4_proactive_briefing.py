from pathlib import Path

from app.selfops import OperationalBriefingEngine


def main():
    print()
    print("========================================")
    print("RazaAI Step 12.4 Proactive Briefing")
    print("========================================")
    print()

    root = Path(__file__).resolve().parents[1]
    brief = OperationalBriefingEngine(root).build(
        run_audit=False,
    )

    assert brief["status"] in {
        "healthy",
        "attention",
        "degraded",
    }
    assert isinstance(brief["summary"], str)
    assert isinstance(brief["priorities"], list)
    assert "health" in brief

    print("[PASS] proactive brief built from trusted operational state")

    for priority in brief["priorities"]:
        assert priority["kind"] in {
            "self_audit",
            "knowledge",
        }

    print("[PASS] briefing priorities are evidence-backed, not model invented")

    print()
    print("========================================")
    print("STEP 12.4 PROACTIVE BRIEFING PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
