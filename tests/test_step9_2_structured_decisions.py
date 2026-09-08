from app.playbooks import PlaybookEngine, PlaybookDecisionEvaluator


def fresh():
    engine = PlaybookEngine()
    evaluator = PlaybookDecisionEvaluator()
    match = engine.match(
        "NPS authentication succeeds but Wi-Fi cannot join",
        expert="networking",
    )
    if not match:
        raise AssertionError("Wi-Fi playbook did not match")
    session = engine.start_session(match)
    return engine, evaluator, match, session


def main():
    print()
    print("========================================")
    print("RazaAI Step 9.2 Structured Decision Test")
    print("========================================")
    print()

    engine, evaluator, match, session = fresh()

    d = evaluator.evaluate(
        match.playbook,
        session,
        "It's set to VLAN 80.",
    )

    if d.decision != "unclear":
        raise AssertionError(
            f"Expected unclear, got {d.decision}"
        )

    if "site" not in d.missing_evidence or "ssid" not in d.missing_evidence:
        raise AssertionError(
            f"Expected site/ssid missing evidence, got {d.missing_evidence}"
        )

    print("[PASS] VLAN 80 alone remains UNCLEAR")
    print(f"       missing={d.missing_evidence}")

    engine, evaluator, match, session = fresh()

    d = evaluator.evaluate(
        match.playbook,
        session,
        "Clare, Example-Staff, VLAN 80",
    )

    if d.decision != "passed":
        raise AssertionError(
            f"Expected passed, got {d.decision}: {d.reason}"
        )

    print("[PASS] Clare Staff VLAN 80 -> PASSED")

    engine, evaluator, match, session = fresh()

    d = evaluator.evaluate(
        match.playbook,
        session,
        "Clare, Example-Staff, VLAN 30",
    )

    if d.decision != "isolated":
        raise AssertionError(
            f"Expected isolated, got {d.decision}: {d.reason}"
        )

    if d.evidence.get("expected_vlan") != 80:
        raise AssertionError("Expected Clare Staff VLAN 80")

    print("[PASS] Clare Staff VLAN 30 -> ISOLATED")

    engine, evaluator, match, session = fresh()

    d = evaluator.evaluate(
        match.playbook,
        session,
        "Balaklava, Example-Staff, VLAN 30",
    )

    if d.decision != "passed":
        raise AssertionError(
            f"Expected passed, got {d.decision}: {d.reason}"
        )

    print("[PASS] Balaklava Staff VLAN 30 -> PASSED")

    # Simulate Python-controlled advancement.
    d = evaluator.evaluate(
        match.playbook,
        session,
        "Balaklava, Example-Staff, VLAN 30",
    )

    if d.decision == "passed":
        session.advance(match.playbook)

    if session.current_step != 1:
        raise AssertionError("Python did not advance to DHCP step")

    print("[PASS] PASSED decision advances Python state to step 2")

    d2 = evaluator.evaluate(
        match.playbook,
        session,
        "The client has 169.254.10.25",
    )

    if d2.decision != "isolated":
        raise AssertionError(
            f"Expected DHCP isolated, got {d2.decision}"
        )

    print("[PASS] APIPA on step 2 -> ISOLATED")

    print()
    print("========================================")
    print("STEP 9.2 STRUCTURED DECISIONS PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
