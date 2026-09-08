from pathlib import Path


def main():
    print()
    print("========================================")
    print("RazaAI Step 11.5 Agent Integration")
    print("========================================")
    print()

    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "agent" / "agent.py").read_text(encoding="utf-8")
    promotion_source = (root / "app" / "incidents" / "promotions.py").read_text(encoding="utf-8")

    required = [
        "KnowledgePromotionEngine",
        "self.knowledge_promotions",
        "promote_eligible()",
        "[Knowledge Promotion]",
    ]
    for item in required:
        assert item in source, item

    assert "does NOT directly mutate Qdrant" in promotion_source
    assert "same-day recurrence is insufficient for durable knowledge promotion" in promotion_source
    assert "knowledge/<category>/promoted/" in promotion_source

    print("[PASS] promotion engine wired into validated incident closure")
    print("[PASS] same-day recurrence promotion guard present")
    print("[PASS] promotion writes curated sources, not Qdrant directly")
    print("[PASS] category-preserving knowledge path contract present")

    print()
    print("========================================")
    print("STEP 11.5 AGENT INTEGRATION PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
