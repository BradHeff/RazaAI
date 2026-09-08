from app.infrastructure.aruba import (
    ArubaReadOnlyAdapter,
    AOS_CX_CHECKS,
    AOS_SWITCH_CHECKS,
)


def main():
    print()
    print("========================================")
    print("RazaAI Step 10.1 Aruba Adapter Test")
    print("========================================")
    print()

    cx = ArubaReadOnlyAdapter.checks_for_platform(
        "aos-cx"
    )

    required_cx = [
        "system",
        "version",
        "interfaces",
        "vlans",
        "mac_table",
        "lldp",
        "spanning_tree",
        "routes",
        "arp",
        "lacp",
        "poe",
    ]

    for check in required_cx:
        if check not in cx:
            raise AssertionError(
                f"Missing AOS-CX check: {check}"
            )

    print(
        "[PASS] AOS-CX 6100 allowlist"
    )

    aos = (
        ArubaReadOnlyAdapter
        .checks_for_platform(
            "aos-switch"
        )
    )

    required_aos = [
        "system",
        "version",
        "interfaces",
        "vlans",
        "mac_table",
        "lldp",
        "spanning_tree",
        "routes",
        "arp",
        "trunks",
    ]

    for check in required_aos:
        if check not in aos:
            raise AssertionError(
                f"Missing ArubaOS-Switch check: "
                f"{check}"
            )

    print(
        "[PASS] ArubaOS-Switch 2930M allowlist"
    )

    if (
        AOS_CX_CHECKS["interfaces"]
        == AOS_SWITCH_CHECKS["interfaces"]
    ):
        raise AssertionError(
            "Platform-specific interface commands "
            "were not separated"
        )

    print(
        "[PASS] platform-specific CLI kept separate"
    )

    dangerous_terms = [
        "configure",
        "write memory",
        "erase",
        "reload",
        "reboot",
        "delete",
        "clear ",
        "no ",
        "set ",
    ]

    for platform_name, checks in [
        ("aos-cx", AOS_CX_CHECKS),
        ("aos-switch", AOS_SWITCH_CHECKS),
    ]:
        for name, command in checks.items():
            lower = command.lower()

            for term in dangerous_terms:
                if lower.startswith(term):
                    raise AssertionError(
                        f"Potential write command in "
                        f"{platform_name}/{name}: "
                        f"{command}"
                    )

    print(
        "[PASS] Aruba allowlists contain read-only "
        "show/get-style checks only"
    )

    print()
    print("========================================")
    print("STEP 10.1 ARUBA SWITCHES PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
