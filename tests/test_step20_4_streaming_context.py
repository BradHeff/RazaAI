"""RazaAI streaming + local context budgeting."""

import json
from pathlib import Path
from unittest.mock import patch

from app.context_budget import compact_messages, estimate_messages
from app.ollama_client import OllamaClient


class _StreamingResponse:
    def __init__(self, events):
        self.lines = [json.dumps(item).encode("utf-8") + b"\n" for item in events]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self.lines)


def main():
    print("=" * 72)
    print("RazaAI Step 20.4 Streaming + Context Budget")
    print("=" * 72)

    system = "CORE CONTRACT\n" + ("authoritative guidance " * 160)
    history = []
    for i in range(18):
        history.append({"role": "user", "content": f"old question {i} " + ("x" * 500)})
        history.append({"role": "assistant", "content": f"old answer {i} " + ("y" * 500)})
    evidence = {
        "role": "tool",
        "content": "CURRENT EVIDENCE\nNEC internal call over IPsec VPN",
    }
    current = {
        "role": "user",
        "content": "what if i want to check 1 way audio on NEC phone for internal calls between campus over ipsec VPN tunnel?",
    }
    messages = [{"role": "system", "content": system}, *history, evidence, current]

    compacted, report = compact_messages(
        messages,
        context_window=4096,
        reserve_output_tokens=700,
    )
    assert report["history_messages_removed"] > 0
    assert report["estimated_after_tokens"] <= report["prompt_limit_tokens"]
    assert compacted[-1]["content"] == current["content"]
    assert any("CURRENT EVIDENCE" in str(m.get("content")) for m in compacted)
    assert not any("old question 0" in str(m.get("content")) for m in compacted)
    print("[PASS] oversized turns drop oldest chat while preserving current request/evidence")

    captured = {}
    chunks = []
    events = [
        {"message": {"role": "assistant", "content": "Check "}, "done": False},
        {"message": {"role": "assistant", "content": "RTP first."}, "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True},
    ]

    def fake_urlopen(request, timeout=300):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _StreamingResponse(events)

    client = OllamaClient(
        host="http://127.0.0.1:11434",
        model="raza-edge:4b-v3",
        num_ctx=None,
        keep_alive="30m",
    )
    with patch("app.ollama_client.urllib.request.urlopen", fake_urlopen):
        result = client.chat_stream(
            [{"role": "user", "content": "test"}],
            on_chunk=chunks.append,
        )

    assert captured["payload"]["stream"] is True
    assert captured["payload"]["think"] is False
    assert captured["payload"]["keep_alive"] == "30m"
    assert chunks == ["Check ", "RTP first."]
    assert result["message"]["content"] == "Check RTP first."
    print("[PASS] Ollama NDJSON chunks stream incrementally and reconstruct final answer")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    tui = Path("app/tui/app.py").read_text(encoding="utf-8")
    config = Path("app/config.py").read_text(encoding="utf-8")

    assert "compact_messages(" in agent
    assert "self.client.chat_stream(" in agent
    assert "not web_needs_grounding" in agent
    assert "tools_for_turn is None" in agent
    print("[PASS] streaming is restricted to no-model-tool, non-web-grounding responses")

    assert "call_from_thread" in tui
    assert "StreamingMessage" in tui
    assert "Generating" in tui
    assert "asyncio.to_thread" in tui
    print("[PASS] TUI streams on its UI thread while inference remains off-loop")

    assert "RAZAAI_OLLAMA_CONTEXT_WINDOW" in config
    assert "RAZAAI_OLLAMA_OUTPUT_RESERVE" in config
    print("[PASS] context window and output reserve are configurable for host/edge profiles")

    print()
    print("=" * 72)
    print("STEP 20.4 STREAMING + CONTEXT BUDGET PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
