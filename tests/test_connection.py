from app.ollama_client import OllamaClient


def main():
    client = OllamaClient()

    response = client.chat([
        {
            "role": "user",
            "content": "Reply with exactly: RazaAI connection successful.",
        }
    ])

    print(response)


if __name__ == "__main__":
    main()
