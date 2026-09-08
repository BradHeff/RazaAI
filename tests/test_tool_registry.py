from app.tools.registry import ToolRegistry


def main():

    registry = ToolRegistry()

    print()
    print("========================================")
    print("RazaAI Tool Registry")
    print("========================================")
    print()

    for tool in registry.list_tools():

        print(f"Name:       {tool['name']}")
        print(f"Category:   {tool['category']}")
        print(f"Risk:       {tool['risk']}")
        print(f"Permission: {tool['permission']}")
        print(f"Timeout:    {tool['timeout']}")
        print()


if __name__ == "__main__":
    main()
