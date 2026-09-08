from app.infrastructure.aruba_port import (
    validate_port,
    _cx_commands,
    _aos_switch_commands,
)


def main():
    print()
    print("========================================")
    print("RazaAI Step 10.2 Aruba Port Test")
    print("========================================")
    print()

    assert (
        validate_port(
            "aos-cx",
            "1/1/5",
        )
        == "1/1/5"
    )

    print(
        "[PASS] AOS-CX port validation"
    )

    assert (
        validate_port(
            "aos-switch",
            "24",
        )
        == "24"
    )

    assert (
        validate_port(
            "aos-switch",
            "A1",
        )
        == "A1"
    )

    print(
        "[PASS] ArubaOS-Switch port validation"
    )

    for bad in [
        "1/1/5; configure terminal",
        "../../etc/passwd",
        "1 && reload",
    ]:
        try:
            validate_port(
                "aos-cx",
                bad,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"Unsafe port value accepted: "
                f"{bad}"
            )

    print(
        "[PASS] unsafe AOS-CX port values rejected"
    )

    cx = _cx_commands(
        "1/1/5"
    )

    for required in [
        "status",
        "counters",
        "vlans",
        "macs",
        "lldp",
        "poe",
        "lacp",
    ]:
        if required not in cx:
            raise AssertionError(
                f"Missing CX port check: "
                f"{required}"
            )

    print(
        "[PASS] AOS-CX targeted check set"
    )

    aos = _aos_switch_commands(
        "24"
    )

    for required in [
        "status",
        "counters",
        "vlans",
        "macs",
        "lldp",
        "poe",
        "trunks",
    ]:
        if required not in aos:
            raise AssertionError(
                f"Missing AOS-S port check: "
                f"{required}"
            )

    print(
        "[PASS] ArubaOS-Switch targeted check set"
    )

    print()
    print("========================================")
    print("STEP 10.2 ARUBA PORT DIAGNOSTICS PASSED")
    print("========================================")
    print()


if __name__ == "__main__":
    main()
