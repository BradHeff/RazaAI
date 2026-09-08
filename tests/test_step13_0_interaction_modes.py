from app.interaction import InteractionRouter
from app.experts import ExpertRouter


def classify(router, experts, text, previous=None):
    return router.classify(text, expert_route=experts.route(text), previous=previous)


def main():
    print()
    print("========================================")
    print("RazaAI Step 13.0 Interaction Modes")
    print("========================================")
    print()

    router = InteractionRouter()
    experts = ExpertRouter()

    c = classify(router, experts, "What capabilities can you do?")
    assert c.mode == "conversation" and not c.allow_tools
    print("[PASS] capability question remains conversation, not tool action")

    c = classify(router, experts, "Can you see files within your code base?")
    assert c.mode == "conversation" and not c.allow_tools
    print("[PASS] technical nouns alone do not trigger task mode")

    c = classify(router, experts, "Check the system status of aruba-core-6100")
    assert c.mode == "action" and c.allow_tools
    print("[PASS] explicit operation enters action mode")

    c = classify(router, experts, "The Wi-Fi client is offline")
    assert c.mode == "troubleshooting" and c.allow_tools
    print("[PASS] active fault enters troubleshooting mode")

    print()
    print("========================================")
    print("STEP 13.0 INTERACTION MODES PASSED")
    print("========================================")


if __name__ == "__main__":
    main()
