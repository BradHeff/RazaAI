from app.agent import RazaAgent


def main():

    agent = RazaAgent()

    print()
    print("========================================")
    print("RazaAI Agent Tool Test")
    print("========================================")
    print()

    response = agent.ask(
        "Use the get_system_info tool to determine "
        "what operating system this RazaAI server "
        "is running. Then tell me what you found."
    )

    print()
    print("========================================")
    print("FINAL RazaAI RESPONSE")
    print("========================================")
    print()
    print(response)
    print()


if __name__ == "__main__":
    main()
