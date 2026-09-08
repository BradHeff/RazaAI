from app.knowledge import KnowledgeEngine
from app.tools.registry import ToolRegistry


CASES = [
    (
        "networking",
        "What change fixed Wi-Fi throughput capped around 315 Mbps on Aruba AP-515 access points?",
        "80 MHz",
    ),
    (
        "networking",
        "NPS grants Wi-Fi access but a client still cannot join on Ruckus. What configuration fault was seen?",
        "VLAN",
    ),
    (
        "microsoft",
        "What caused Linewize LDAPS synchronization failure at the example campus?",
        "domain controller",
    ),
    (
        "servers",
        (
            "Plex VM says the LXD VM agent isn't currently running, "
            "the console drops to initramfs, and the ext4 root filesystem "
            "is corrupted. What filesystem repair command fixed it?"
        ),
        "fsck.ext4",
    ),
]


def main():
    print()
    print("========================================")
    print("RazaAI Step 6 School ICT Corpus Test")
    print("========================================")
    print()

    engine = KnowledgeEngine()

    try:
        ingestion = engine.ingest_all()
        indexed = sum(
            1 for item in ingestion["documents"]
            if item["status"] == "indexed"
        )
        unchanged = sum(
            1 for item in ingestion["documents"]
            if item["status"] == "unchanged"
        )

        print(
            f"[PASS] corpus ingestion: {indexed} indexed, "
            f"{unchanged} unchanged"
        )

        for category, query, expected in CASES:
            results = engine.search(
                query,
                top_k=10,
                category=category,
            )

            joined = "\n".join(
                item["text"] for item in results
            ).lower()

            if expected.lower() not in joined:
                raise AssertionError(
                    f"Expected '{expected}' not found for query: {query}"
                )

            print(
                f"[PASS] {category}: retrieved '{expected}'"
            )

    finally:
        engine.close()

    registry = ToolRegistry()

    result = registry.execute(
        "search_knowledge",
        {
            "query": (
                "Why might a school Wi-Fi client authenticate successfully "
                "with NPS but still fail to get onto the network?"
            ),
            "category": "networking",
            "top_k": 5,
        },
    )

    if not result.success:
        raise AssertionError(
            f"search_knowledge failed: {result.error}"
        )

    if not result.result["results"]:
        raise AssertionError(
            "search_knowledge returned no school ICT results"
        )

    print("[PASS] agent knowledge tool can retrieve school ICT field notes")

    print()
    print("========================================")
    print("STEP 6 SCHOOL ICT CORPUS PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
