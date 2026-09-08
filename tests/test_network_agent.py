from app.agent import RazaAgent


def main():

    agent = RazaAgent()

    print()
    print("========================================")
    print("RazaAI Network Agent Test")
    print("========================================")
    print()

    response = agent.ask(
        "Inspect this computer's network interfaces. "
        "Tell me which interfaces are currently up, "
        "and list their IPv4 addresses."
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
