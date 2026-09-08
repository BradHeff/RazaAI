from app.ollama_client import OllamaClient
from app.tools.registry import ToolRegistry


def main():
    client = OllamaClient()
    registry = ToolRegistry()

    tools = registry.get_definitions()

    messages = [
        {
            "role": "user",
            "content": (
                "Use the get_system_info tool to find out what "
                "operating system this RazaAI server is running."
            ),
        }
    ]

    print("Sending request to RazaAI...")
    print()

    response = client.chat(
        messages,
        tools=tools,
    )

    print("Raw Ollama response:")
    print(response)

    print()
    print("Message:")
    print(response.get("message"))


if __name__ == "__main__":
    main()
