from app.diagnostics.live_evidence import (
    LiveEvidenceCollector,
)


def main():
    print()
    print("========================================")
    print("RazaAI Step 10.3.1 Auto Live Evidence")
    print("========================================")
    print()

    collector = LiveEvidenceCollector()

    # Parser-level check only; don't hit real infrastructure in unit test.
    pb = {
        "id": "aruba-port-connectivity",
    }

    missing = collector.collect(
        "The AP on aruba-core-6100 is offline",
        playbook=pb,
    )

    if missing["collected"]:
        raise AssertionError(
            "Collector should require a port"
        )

    if "port" not in missing["missing"]:
        raise AssertionError(
            "Missing port was not detected"
        )

    print("[PASS] missing port is detected")

    guidance = collector.guidance({
        "collected": True,
        "host": "aruba-core-6100",
        "port": "1/1/5",
        "result": {
            "primary_finding": (
                "Port 1/1/5 has no physical link."
            ),
            "severity": "high",
            "next_check": (
                "Check cable/device power."
            ),
            "evidence": {
                "admin_up": True,
                "link_up": False,
            },
        },
    })

    for required in [
        "LIVE INFRASTRUCTURE EVIDENCE",
        "Do NOT ask the user to run",
        "Port 1/1/5 has no physical link",
    ]:
        if required not in guidance:
            raise AssertionError(
                f"Missing guidance: {required}"
            )

    print("[PASS] live evidence guidance prevents tool hand-off")
    print("[PASS] primary finding is injected into model context")

    print()
    print("========================================")
    print("STEP 10.3.1 AUTO LIVE EVIDENCE PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
