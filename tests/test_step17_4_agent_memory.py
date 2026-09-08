"""RazaAI application memory integration."""

from pathlib import Path
import os
import tempfile

from app.agent.agent import RazaAgent


class FakeOllama:
    def __init__(self):
        self.seen_memory = False

    def chat(self, messages, tools=None):
        memory_text = "\n".join(
            message.get("content", "")
            for message in messages
            if message.get("role") == "tool"
            and "UNTRUSTED_PERSISTENT_MEMORY" in message.get("content", "")
        )
        if "Brad Heffernan" in memory_text:
            self.seen_memory = True
            return {
                "message": {
                    "role": "assistant",
                    "content": "You previously told me your name is Brad Heffernan.",
                }
            }
        return {
            "message": {
                "role": "assistant",
                "content": "Understood.",
            }
        }


def main():
    print("=" * 68)
    print("RazaAI Step 17.4 Agent Memory Integration")
    print("=" * 68)

    with tempfile.TemporaryDirectory() as temp:
        previous = os.environ.get("RAZAAI_MEMORY_DIR")
        os.environ["RAZAAI_MEMORY_DIR"] = temp
        try:
            first = RazaAgent()
            first.client = FakeOllama()
            first.ask("my name is Brad Heffernan")

            memory_file = Path(temp) / "memories.json"
            assert memory_file.exists()
            print("[PASS] direct user fact persists from normal application turn")

            # New agent instance proves process/session persistence.
            second = RazaAgent()
            fake = FakeOllama()
            second.client = fake
            response = second.ask("write a short greeting using my name")
            assert fake.seen_memory
            assert "Brad Heffernan" in response
            print("[PASS] new agent session receives relevant persistent memory")

            # Explicit deterministic recall should not require model cooperation.
            response = second.ask("what is my name?")
            assert "Brad Heffernan" in response
            print("[PASS] explicit memory recall is Python-authoritative")

            response = second.ask("forget Brad Heffernan")
            assert "Forgot" in response
            print("[PASS] explicit forget is Python-authoritative")

            third = RazaAgent()
            third.client = FakeOllama()
            response = third.ask("what is my name?")
            assert "don't have a matching" in response
            print("[PASS] forgotten memory stays unavailable in later session")
        finally:
            if previous is None:
                os.environ.pop("RAZAAI_MEMORY_DIR", None)
            else:
                os.environ["RAZAAI_MEMORY_DIR"] = previous

    print()
    print("=" * 68)
    print("STEP 17.4 AGENT MEMORY INTEGRATION PASSED")
    print("=" * 68)


if __name__ == "__main__":
    main()
