from pathlib import Path

from app.knowledge.chunking import split_markdown_incidents
from app.knowledge import KnowledgeEngine
from app.knowledge.config import KNOWLEDGE_DIR


def main():
    print()
    print("========================================")
    print("RazaAI Step 8.2 Incident Chunking Test")
    print("========================================")
    print()

    source = (
        KNOWLEDGE_DIR
        / "networking"
        / "school-networking-field-notes.md"
    )

    if not source.exists():
        raise AssertionError(
            f"Expected school field notes missing: {source}"
        )

    text = source.read_text(
        encoding="utf-8",
        errors="replace",
    )

    sections = split_markdown_incidents(text)

    if len(sections) < 5:
        raise AssertionError(
            "Markdown was not split into enough incident sections"
        )

    print(
        f"[PASS] Markdown split into {len(sections)} logical section(s)"
    )

    nps_sections = [
        item for item in sections
        if item.get("heading")
        and "nps" in item["heading"].lower()
        and "wi-fi" in item["heading"].lower()
    ]

    if not nps_sections:
        raise AssertionError(
            "Could not find NPS/Wi-Fi incident heading"
        )

    print(
        "[PASS] NPS/Wi-Fi incident isolated by heading"
    )

    nps_text = nps_sections[0]["text"].lower()

    if "traceroute shows all stars" in nps_text:
        raise AssertionError(
            "Unrelated FortiGate traceroute incident leaked "
            "into NPS/Wi-Fi incident section"
        )

    print(
        "[PASS] adjacent traceroute incident is not mixed into NPS case"
    )

    engine = KnowledgeEngine()

    try:
        result = engine.ingest_file(
            source,
            force=True,
        )

        if result["status"] != "indexed":
            raise AssertionError(
                f"Expected forced reindex, got {result}"
            )

        print(
            f"[PASS] field notes reindexed into "
            f"{result['chunks']} incident-aware chunk(s)"
        )

        results = engine.search(
            (
                "NPS authentication succeeds but the school Wi-Fi "
                "client cannot join because of the access VLAN"
            ),
            top_k=5,
            category="networking",
        )

        if not results:
            raise AssertionError(
                "No results returned after incident-aware reindex"
            )

        best = results[0]
        best_text = best["text"].lower()
        heading = (
            best.get("citation", {})
            .get("heading")
        )

        if "nps" not in best_text or "vlan" not in best_text:
            raise AssertionError(
                "Top result is not the expected NPS/VLAN incident"
            )

        if "traceroute shows all stars" in best_text:
            raise AssertionError(
                "Top result still contains unrelated traceroute incident"
            )

        print(
            f"[PASS] top retrieval is isolated NPS/VLAN incident"
        )

        print(
            f"       heading={heading!r}"
        )

    finally:
        engine.close()

    print()
    print("========================================")
    print("STEP 8.2 INCIDENT CHUNKING PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
