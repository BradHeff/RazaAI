from app.interaction import InteractionRouter
from app.experts import ExpertRouter


def main():
    print()
    print("========================================")
    print("RazaAI Step 13.1 Contextual Conversation")
    print("========================================")
    print()

    ir = InteractionRouter()
    er = ExpertRouter()

    first = ir.classify("hi", expert_route=er.route("hi"))
    second = ir.classify("nothing", expert_route=er.route("nothing"), previous=first)
    assert first.mode == "conversation"
    assert second.mode == "conversation"
    assert second.allow_tools is False
    print("[PASS] short casual follow-up preserves conversation mode")

    advice = ir.classify(
        "Let's discuss storing passwords in a text file",
        expert_route=er.route("Let's discuss storing passwords in a text file"),
    )
    follow = ir.classify("what?", expert_route=er.route("what?"), previous=advice)
    assert advice.mode == "advice" and advice.sensitive
    assert follow.mode == "advice" and follow.sensitive
    print("[PASS] short follow-up retains sensitive advice context")

    action = ir.classify(
        "show it",
        expert_route=er.route("show it"),
        previous=advice,
    )
    assert action.mode == "sensitive_action"
    assert action.allow_tools is False
    print("[PASS] later action inherits sensitive boundary")

    print()
    print("========================================")
    print("STEP 13.1 CONTEXTUAL CONVERSATION PASSED")
    print("========================================")


if __name__ == "__main__":
    main()
