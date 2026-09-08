from app.experts import ExpertRouter
from app.playbooks import PlaybookEngine


CASES = [
    ("NPS authentication succeeds but Wi-Fi cannot join", "wifi-nps-no-connectivity"),
    ("DNS cannot resolve internal hostnames", "dns-resolution-failure"),
    ("LXD VM is stuck in initramfs and fsck may be needed", "lxd-vm-initramfs"),
    ("Intune app failed remediation on a laptop", "intune-app-failure"),
    ("User cannot log in due to domain authentication", "domain-auth-failure"),
    ("Server filesystem is full and has no space", "server-storage-pressure"),
    ("GPO printer deployment is missing", "printer-deployment-failure"),
]


def main():
    print()
    print("========================================")
    print("RazaAI Step 9 Diagnostic Playbook Test")
    print("========================================")
    print()

    router = ExpertRouter()
    engine = PlaybookEngine()

    if len(engine.playbooks) < 7:
        raise AssertionError("Expected at least 7 playbooks")

    print(f"[PASS] loaded {len(engine.playbooks)} playbooks")

    for query, expected in CASES:
        route = router.route(query)
        match = engine.match(query, expert=route.expert)

        if not match:
            raise AssertionError(f"No playbook matched: {query}")

        if match.id != expected:
            raise AssertionError(
                f"Expected {expected}, got {match.id} for: {query}"
            )

        print(f"[PASS] {expected}")

    no_match = engine.match(
        "Explain what an Ethernet frame is",
        expert="networking",
    )

    if no_match is not None:
        raise AssertionError(
            "Explanatory query incorrectly matched a diagnostic playbook"
        )

    print("[PASS] normal technical explanation does not trigger a playbook")

    wifi = engine.match(
        "NPS authentication succeeds but Wi-Fi cannot join",
        expert="networking",
    )

    if not wifi:
        raise AssertionError(
            "Wi-Fi playbook did not match"
        )

    session = engine.start_session(
        wifi
    )

    guidance = engine.guidance(
        wifi,
        session,
        continuation=False,
    )

    for required in [
        "Present ONLY the current check",
        "Do not show later checks",
        "Never invent observations or completed checks",
    ]:
        if required not in guidance:
            raise AssertionError(
                f"Missing playbook rule: {required}"
            )
    print("[PASS] progressive diagnostic rules present")

    print()
    print("========================================")
    print("STEP 9 DIAGNOSTIC PLAYBOOKS PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
