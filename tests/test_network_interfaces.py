from app.tools.registry import ToolRegistry


def main():

    registry = ToolRegistry()

    print()
    print("========================================")
    print("RazaAI Network Interface Test")
    print("========================================")
    print()

    result = registry.execute(
        "get_network_interfaces"
    )

    if not result.success:
        print(f"Tool failed: {result.error}")
        raise SystemExit(1)

    print(
        f"Execution time: "
        f"{result.execution_time:.3f}s"
    )

    print()

    for interface_name, interface in result.result.items():

        print(f"Interface: {interface_name}")
        print(f"  Up:    {interface['is_up']}")
        print(f"  Speed: {interface['speed_mbps']} Mbps")
        print(f"  MTU:   {interface['mtu']}")

        for address in interface["addresses"]:

            print(
                f"  {address['family']}: "
                f"{address['address']}"
            )

        print()


if __name__ == "__main__":
    main()
