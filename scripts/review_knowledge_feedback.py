from app.incidents import IncidentStore, KnowledgeFeedbackEngine


def main():
    store = IncidentStore()
    engine = KnowledgeFeedbackEngine(store)

    print("\n========================================")
    print("RazaAI Knowledge Feedback")
    print("========================================\n")

    results = engine.refresh_all()

    if not results:
        print("No promoted knowledge sources currently require feedback evaluation.")
        return

    for item in results:
        print(
            f"[{item.knowledge_status.upper():7}] {item.fingerprint} "
            f"score={item.confidence_score:.2f} "
            f"confirm={item.confirmations} "
            f"contradict={item.contradictions} "
            f"stale_days={item.stale_days}"
        )
        print(f"          {item.reason}")

    print("\nRun `python3 -m scripts.ingest_knowledge` after feedback changes")
    print("so updated promoted-knowledge metadata is reflected in Qdrant.\n")


if __name__ == "__main__":
    main()
