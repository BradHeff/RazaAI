from app.interaction import InteractionRouter, InteractionContext


def main():
    print()
    print("========================================")
    print("RazaAI Step 13.4 Personality Mode Adaptation")
    print("========================================")
    print()

    router = InteractionRouter()

    conversation = InteractionContext(
        mode="conversation", domain=None, action_requested=False,
        sensitive=False, sensitive_kind=None, troubleshooting=False,
        allow_tools=False, reason="test",
    )
    cg = router.guidance(conversation)
    assert "Personality may be more visible" in cg
    assert "Do not call tools" in cg
    print("[PASS] conversation mode allows personality without tools")

    troubleshooting = InteractionContext(
        mode="troubleshooting", domain="networking", action_requested=False,
        sensitive=False, sensitive_kind=None, troubleshooting=True,
        allow_tools=True, reason="test",
    )
    tg = router.guidance(troubleshooting)
    assert "Evidence and diagnostic state outrank personality" in tg
    print("[PASS] troubleshooting mode prioritises evidence over sass")

    sensitive = InteractionContext(
        mode="advice", domain="cybersecurity", action_requested=False,
        sensitive=True, sensitive_kind="credentials", troubleshooting=False,
        allow_tools=False, reason="test",
    )
    sg = router.guidance(sensitive)
    assert "password manager" in sg
    assert "concise dry/sarcastic" in sg  # Wording updated from "brief dry remark"
    print("[PASS] sensitive advice keeps security guidance while allowing light personality")

    print()
    print("========================================")
    print("STEP 13.4 PERSONALITY MODE ADAPTATION PASSED")
    print("========================================")


if __name__ == "__main__":
    main()
