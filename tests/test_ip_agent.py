from app.agent import RazaAgent


def main():

    agent = RazaAgent()

    print()
    print("========================================")
    print("RazaAI IP Agent Test")
    print("========================================")
    print()

    response = agent.ask(
        "Inspect this computer's current IP configuration. "
        "Tell me its IPv4 addresses, default gateway, and "
        "configured DNS servers. Use the appropriate live tool."
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
