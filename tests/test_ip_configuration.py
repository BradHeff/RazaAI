from app.tools.registry import ToolRegistry


def main():

    registry = ToolRegistry()

    print()
    print("========================================")
    print("RazaAI IP Configuration Test")
    print("========================================")
    print()

    result = registry.execute(
        "get_ip_configuration"
    )

    if not result.success:
        print(f"Tool failed: {result.error}")
        raise SystemExit(1)

    data = result.result

    print(f"Hostname:        {data['hostname']}")
    print(f"Default gateway: {data['default_gateway']}")
    print(
        "DNS servers:    "
        + ", ".join(data["dns_servers"])
    )

    print()

    for interface_name, interface in data["interfaces"].items():

        print(f"Interface: {interface_name}")
        print(f"  Up: {interface['is_up']}")

        for address in interface["ipv4"]:
            print(
                f"  IPv4: {address['address']} "
                f"Netmask: {address['netmask']}"
            )

        for address in interface["ipv6"]:
            print(
                f"  IPv6: {address['address']}"
            )

        print()

    print(
        f"Execution time: "
        f"{result.execution_time:.3f}s"
    )


if __name__ == "__main__":
    main()
