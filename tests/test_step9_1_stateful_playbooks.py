from app.playbooks import PlaybookEngine


def main():
    print()
    print("========================================")
    print("RazaAI Step 9.1 Stateful Playbook Test")
    print("========================================")
    print()

    engine = PlaybookEngine()
    match = engine.match(
        "NPS authentication succeeds but Wi-Fi cannot join",
        expert="networking",
    )

    if not match:
        raise AssertionError("Wi-Fi playbook did not match")

    print(f"[PASS] matched {match.id}")

    session = engine.start_session(match)

    if session.current_step != 0:
        raise AssertionError("Session did not start at step 1")

    if session.status != "waiting_for_evidence":
        raise AssertionError("Incorrect initial session status")

    print("[PASS] session starts at step 1 waiting for evidence")

    first = session.current_check(match.playbook)
    if "Access VLAN" not in first:
        raise AssertionError(
            f"Expected Access VLAN first check, got: {first}"
        )

    print("[PASS] first check is Access VLAN verification")

    start_guidance = engine.guidance(
        match,
        session,
        continuation=False,
    )

    if "Present ONLY the current check" not in start_guidance:
        raise AssertionError("Start guidance does not enforce one check")

    print("[PASS] initial response constrained to current check only")

    session.add_observation("Access VLAN is 80 and correct for Clare.")
    advanced = session.advance(match.playbook)

    if not advanced or session.current_step != 1:
        raise AssertionError("Session did not advance to step 2")

    second = session.current_check(match.playbook)
    if "DHCP" not in second:
        raise AssertionError(
            f"Expected DHCP second check, got: {second}"
        )

    print("[PASS] session advances to DHCP only after step 1")

    continuation = engine.guidance(
        match,
        session,
        continuation=True,
    )

    for required in [
        "CAUSE ISOLATED",
        "CURRENT CHECK PASSED",
        "RESULT UNCLEAR",
        "Do not restart the playbook",
    ]:
        if required not in continuation:
            raise AssertionError(
                f"Missing continuation rule: {required}"
            )

    print("[PASS] continuation has strict three-outcome state rules")

    session.resolve()
    if session.status != "resolved":
        raise AssertionError("Session did not resolve")

    print("[PASS] session can enter resolved state")

    print()
    print("========================================")
    print("STEP 9.1 STATEFUL PLAYBOOKS PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
