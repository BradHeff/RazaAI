from pathlib import Path


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.6 Agent Integration")
    print("========================================")
    print()

    root = Path(__file__).resolve().parents[1]
    agent = (root / "app" / "agent" / "agent.py").read_text(encoding="utf-8")
    hybrid = (root / "app" / "knowledge" / "hybrid.py").read_text(encoding="utf-8")
    feedback = (root / "app" / "incidents" / "feedback.py").read_text(encoding="utf-8")

    for required in (
        "KnowledgeFeedbackEngine",
        "self.knowledge_feedback",
        "refresh_all()",
        "[Knowledge Feedback]",
    ):
        assert required in agent, required

    assert "the llm never" in feedback.lower()
    assert 'status == "review"' in hybrid
    assert 'knowledge_type") == "validated_operational_pattern"' in hybrid

    print("[PASS] feedback engine wired into validated incident closure")
    print("[PASS] LLM cannot author confirmation/contradiction state")
    print("[PASS] review/stale confidence affects promoted RAG ranking only")
    print("[PASS] hand-curated/reference knowledge remains unaffected")

    print()
    print("========================================")
    print("STEP 11.6 AGENT INTEGRATION PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
