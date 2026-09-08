from app.experts import ExpertRouter
from app.diagnostics import DiagnosticEngine


def main():
    print()
    print("========================================")
    print("RazaAI Step 8.1 Evidence Ranking Test")
    print("========================================")
    print()

    query = (
        "NPS authentication succeeds but the school Wi-Fi client "
        "cannot join properly. What should I check first?"
    )

    router = ExpertRouter()
    diagnostics = DiagnosticEngine()

    route = router.route(query)
    context = diagnostics.build_context(
        query=query,
        route=route,
    )

    if not context.primary_evidence:
        raise AssertionError(
            "No PRIMARY EVIDENCE selected"
        )

    print(
        "[PASS] primary evidence selected"
    )

    print(
        f"       incident_score="
        f"{context.primary_evidence.get('incident_score')}"
    )

    primary_text = (
        context.primary_evidence.get("text", "")
        .lower()
    )

    if "vlan" not in primary_text:
        raise AssertionError(
            "Expected VLAN-related prior incident "
            "to rank as PRIMARY EVIDENCE"
        )

    print(
        "[PASS] VLAN-related incident ranked primary"
    )

    for item in context.secondary_evidence:
        if (
            item.get("incident_score", 0)
            > context.primary_evidence.get(
                "incident_score",
                0,
            )
        ):
            raise AssertionError(
                "Secondary evidence outranked primary"
            )

    print(
        "[PASS] secondary evidence ranked below primary"
    )

    guidance = diagnostics.guidance(
        context
    )

    required = [
        "Base the PRIMARY HYPOTHESIS on PRIMARY EVIDENCE",
        "If you override PRIMARY EVIDENCE",
        "Never present a secondary incident",
    ]

    for rule in required:
        if rule not in guidance:
            raise AssertionError(
                f"Missing evidence ranking rule: {rule}"
            )

    print(
        "[PASS] primary-evidence constraints present"
    )

    print()
    print("PRIMARY EVIDENCE PREVIEW:")
    print("----------------------------------------")
    print(
        context.primary_evidence.get(
            "text",
            "",
        )[:900]
    )
    print("----------------------------------------")

    print()
    print("========================================")
    print("STEP 8.1 EVIDENCE RANKING PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
