from app.knowledge import KnowledgeEngine
from app.tools.registry import ToolRegistry

EXPECTED_PHRASE = "VLAN 731"


def main():

    print()
    print("========================================")
    print("RazaAI Step 4 Knowledge / RAG Test")
    print("========================================")
    print()





    engine = KnowledgeEngine()

    try:

        results = engine.ingest_all()

        print(
            f"[PASS] ingestion: "
            f"{len(results)} document(s), "
            f"{engine.collection_count()} chunks"
        )

        matches = engine.search(
            ("What VLAN is used for the RazaAI " "laboratory management network?"),
            top_k=3,
        )

        if not matches:
            raise AssertionError("Knowledge search returned no results")

        combined = "\n".join(match["text"] for match in matches)

        if EXPECTED_PHRASE not in combined:
            raise AssertionError(
                f"Expected test knowledge " f"'{EXPECTED_PHRASE}' was not retrieved"
            )

        print(f"[PASS] semantic retrieval found " f"{EXPECTED_PHRASE}")

    finally:

        engine.close()





    registry = ToolRegistry()

    names = {tool["name"] for tool in registry.list_tools()}

    if "search_knowledge" not in names:
        raise AssertionError("search_knowledge is not registered")

    tool_result = registry.execute(
        "search_knowledge",
        {
            "query": ("RazaAI laboratory " "management VLAN"),
            "top_k": 3,
        },
    )

    if not tool_result.success:
        raise AssertionError(f"Tool failed: {tool_result.error}")

    if not tool_result.result["results"]:
        raise AssertionError("search_knowledge returned no results")

    print("[PASS] search_knowledge tool")

    best = tool_result.result["results"][0]

    print()
    print("Best result:")
    print(f"  Score:  {best['score']}")
    print(f"  Source: {best.get('source') or (best.get('citation') or {}).get('source')}")
    print(f"  Text:   {best['text'][:300]}")

    print()
    print("========================================")
    print("STEP 4 RAG PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
