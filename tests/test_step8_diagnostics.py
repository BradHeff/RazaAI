from app.experts import ExpertRouter
from app.diagnostics import DiagnosticEngine
from app.agent import RazaAgent


def main():
    print()
    print("========================================")
    print("RazaAI Step 8 Diagnostic Engine Test")
    print("========================================")
    print()

    router = ExpertRouter()
    diagnostics = DiagnosticEngine()

    query = (
        "NPS authentication succeeds but the school Wi-Fi client "
        "cannot join properly. What should I check first?"
    )

    route = router.route(query)
    context = diagnostics.build_context(
        query=query,
        route=route,
    )

    if not context.is_troubleshooting:
        raise AssertionError(
            "Troubleshooting intent was not detected"
        )

    print(
        "[PASS] troubleshooting intent detected"
    )

    if route.expert != "networking":
        raise AssertionError(
            f"Expected networking route, got {route.expert}"
        )

    print(
        "[PASS] expert route is networking"
    )

    if not context.evidence:
        raise AssertionError(
            "Automatic diagnostic retrieval returned no evidence"
        )

    print(
        f"[PASS] automatic retrieval returned "
        f"{len(context.evidence)} evidence result(s)"
    )

    joined = "\n".join(
        item.get("text", "")
        for item in context.evidence
    ).lower()

    if "vlan" not in joined:
        raise AssertionError(
            "Expected VLAN-related school field note was not retrieved"
        )

    print(
        "[PASS] prior VLAN-related field-note evidence retrieved"
    )

    guidance = diagnostics.guidance(context)

    required_rules = [
        "Base the PRIMARY HYPOTHESIS on PRIMARY EVIDENCE",
        "at most TWO alternative hypotheses",
        "From our field notes/knowledge:",
        "From live tools:",
        "Additional diagnosis:",
    ]

    for rule in required_rules:
        if rule not in guidance:
            raise AssertionError(
                f"Missing diagnostic rule: {rule}"
            )

    print(
        "[PASS] precision/evidence rules present"
    )

    print()
    print("Testing live RazaAI diagnostic response...")
    print()

    agent = RazaAgent()

    response = agent.ask(query)

    if not response.strip():
        raise AssertionError(
            "RazaAI returned an empty diagnostic response"
        )

    print()
    print("----------------------------------------")
    print(response)
    print("----------------------------------------")
    print()

    print("========================================")
    print("STEP 8 DIAGNOSTIC ENGINE PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
