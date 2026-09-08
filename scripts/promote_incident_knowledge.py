from app.incidents import IncidentStore, KnowledgePromotionEngine


def main():
    store = IncidentStore()
    engine = KnowledgePromotionEngine(store)
    candidates = engine.evaluate()

    print("\n========================================")
    print("RazaAI Knowledge Promotion")
    print("========================================\n")

    if not candidates:
        print("No validated incident patterns found.")
        return

    for candidate in candidates:
        state = "ELIGIBLE" if candidate.eligible else "BLOCKED"
        print(
            f"[{state:8}] {candidate.fingerprint} "
            f"count={candidate.count} dates={candidate.distinct_dates} "
            f"site={candidate.site or '-'} system={candidate.system or '-'}"
        )
        print(f"           {candidate.reason}")

    results = engine.promote_eligible()
    for result in results:
        print(
            f"[{result.status.upper():8}] {result.knowledge_path}"
        )


if __name__ == "__main__":
    main()
