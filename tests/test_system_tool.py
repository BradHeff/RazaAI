from app.tools.registry import ToolRegistry


def main():
    registry = ToolRegistry()

    print("Available tools:")
    for tool in registry.get_definitions():
        print(f"  - {tool['function']['name']}")

    print()
    print("Executing get_system_info...")
    print()

    result = registry.execute("get_system_info")

    assert result.success, result.error
    for key, value in (result.result or {}).items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
