from app.experts import ExpertRouter
from app.knowledge import KnowledgeEngine
from app.agent import RazaAgent


ROUTES = [
    ("NPS authenticated Wi-Fi but VLAN assignment is wrong", "networking"),
    ("Intune application remediation failed on a Windows laptop", "microsoft"),
    ("LXD VM dropped to initramfs and needs fsck.ext4", "servers"),
    ("Fedora NVIDIA Xorg is crashing", "linux"),
]


def main():
    print()
    print("========================================")
    print("RazaAI Step 7 Expert Routing Test")
    print("========================================")
    print()

    router = ExpertRouter()

    for query, expected in ROUTES:
        route = router.route(query)

        if route.expert != expected:
            raise AssertionError(
                f"Expected route {expected}, got {route.expert}: {query}"
            )

        print(
            f"[PASS] route -> {expected}: "
            f"{route.matched_terms}"
        )

    engine = KnowledgeEngine()

    try:
        results = engine.search(
            (
                "PL01 LXD VM agent is not running, console enters initramfs, "
                "what fsck.ext4 command repaired the filesystem?"
            ),
            top_k=10,
            category="servers",
        )

        joined = "\n".join(item["text"] for item in results).lower()

        if "fsck.ext4" not in joined:
            raise AssertionError(
                "Hybrid retrieval did not surface fsck.ext4"
            )

        if not any(
            item.get("lexical_score", 0) > 0
            for item in results
        ):
            raise AssertionError(
                "Hybrid retrieval produced no lexical score"
            )

        print(
            "[PASS] hybrid retrieval surfaces exact ICT command fsck.ext4"
        )

    finally:
        engine.close()

    print()
    print("Testing live agent route + knowledge search...")
    print()

    agent = RazaAgent()

    response = agent.ask(
        (
            "Search our networking field notes. NPS says authentication "
            "succeeded but the school Wi-Fi client still cannot join properly. "
            "What previously resolved infrastructure issue should I check first? "
            "Separate retrieved field-note evidence from additional diagnosis."
        )
    )

    if not response.strip():
        raise AssertionError("Agent returned an empty response")

    print()
    print("----------------------------------------")
    print(response)
    print("----------------------------------------")
    print()

    print("========================================")
    print("STEP 7 EXPERT ROUTING PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
