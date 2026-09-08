from app.tools.registry import ToolRegistry


def main():

    registry = ToolRegistry()

    print()
    print("========================================")
    print("RazaAI Tool Result Test")
    print("========================================")
    print()

    result = registry.execute(
        "get_system_info"
    )

    print("Result object:")
    print(result)

    print()
    print("Result dictionary:")
    print(result.to_dict())

    print()
    print("Result text:")
    print(result.to_text())

    print()

    assert result.success is True
    assert result.tool == "get_system_info"
    assert result.execution_time >= 0


if __name__ == "__main__":
    main()
