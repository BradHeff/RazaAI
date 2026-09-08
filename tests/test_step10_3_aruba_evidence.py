from app.infrastructure.aruba_evidence import (
    ArubaPortEvidenceAnalyzer,
)


def check(stdout):
    return {
        "success": True,
        "exit_code": 0,
        "stdout": stdout,
        "stderr": "",
    }


def main():
    print()
    print("========================================")
    print("RazaAI Step 10.3 Live Evidence Test")
    print("========================================")
    print()

    analyzer = ArubaPortEvidenceAnalyzer()

    down = analyzer.analyze({
        "port": "1/1/5",
        "platform": "aos-cx",
        "checks": {
            "status": check(
                "Admin state : up\n"
                "Link state : down\n"
                "Speed : 1000"
            ),
            "counters": check(
                "Errors 0\nCRC 0\nDrops 0"
            ),
            "vlans": check(
                "Native VLAN 30\nAllowed VLANs 1,10,30"
            ),
            "macs": check(
                "No entries found"
            ),
            "lldp": check(
                "No neighbors found"
            ),
            "poe": check(
                "Status: searching\nPower: 0 W"
            ),
            "lacp": check(
                "No LACP membership"
            ),
        },
    })

    assert down["evidence"]["admin_up"] is True
    assert down["evidence"]["link_up"] is False
    assert "no physical link" in down["primary_finding"].lower()
    assert "physically connected" in down["next_check"].lower()

    print("[PASS] link-down evidence becomes primary finding")

    up = analyzer.analyze({
        "port": "1/1/7",
        "platform": "aos-cx",
        "checks": {
            "status": check(
                "Admin state : up\n"
                "Link state : up"
            ),
            "counters": check(
                "Errors 0\nCRC 0\nDrops 0"
            ),
            "vlans": check(
                "Native VLAN 30"
            ),
            "macs": check(
                "AA:BB:CC:DD:EE:FF dynamic 1/1/7"
            ),
            "lldp": check(
                "System Name: AP-01\nPort ID: eth0"
            ),
            "poe": check(
                "Power: 8.4 W\nStatus: delivering"
            ),
            "lacp": check(
                "No LACP membership"
            ),
        },
    })

    assert up["evidence"]["link_up"] is True
    assert up["evidence"]["macs_present"] is True
    assert "learning mac" in up["primary_finding"].lower()
    assert "vlan" in up["next_check"].lower()

    print("[PASS] healthy physical link moves diagnosis upward")

    admin_down = analyzer.analyze({
        "port": "1/1/8",
        "platform": "aos-cx",
        "checks": {
            "status": check(
                "Admin state : down\n"
                "Link state : down"
            ),
        },
    })

    assert "administratively disabled" in (
        admin_down["primary_finding"].lower()
    )

    print("[PASS] admin-down outranks other speculation")

    print()
    print("========================================")
    print("STEP 10.3 LIVE EVIDENCE DIAGNOSTICS PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
