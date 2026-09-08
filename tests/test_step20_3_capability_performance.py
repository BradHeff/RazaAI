"""RazaAI capability truth + edge Ollama runtime profile."""

import json
from pathlib import Path
from unittest.mock import patch

from app.agent.edge_router import EdgeIntentRouter
from app.ollama_client import OllamaClient


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(
            {"message": {"role": "assistant", "content": "Hi."}}
        ).encode("utf-8")


def _payload_for(client):
    captured = {}

    def fake_urlopen(request, timeout=300):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response()

    with patch("app.ollama_client.urllib.request.urlopen", fake_urlopen):
        client.chat([{"role": "user", "content": "hi"}])

    return captured["payload"]


def main():
    print("=" * 72)
    print("RazaAI Step 20.3 Capability Truth + Edge Runtime")
    print("=" * 72)

    router = EdgeIntentRouter(manager=object())
    route = router.route("what can you do?")
    assert route.kind == "deterministic_response"
    assert "technical troubleshooting" in route.response
    assert "create DOCX/PDF" in route.response
    assert "grounded read-only public web" in route.response
    assert "remember safe non-secret" in route.response
    assert "self-improvement candidates" in route.response
    assert "protect passwords" in route.response
    assert "inspect passwords" not in route.response
    assert "show credentials" not in route.response
    print("[PASS] overall capability summary is Python-authoritative and security-consistent")

    payload = _payload_for(
        OllamaClient(
            host="http://127.0.0.1:11434",
            model="raza-edge:4b-v3",
            num_ctx=None,
            keep_alive="30m",
        )
    )
    assert "num_ctx" not in payload["options"]
    assert payload["options"]["num_batch"] > 0
    assert payload["keep_alive"] == "30m"
    assert payload["think"] is False
    print("[PASS] default requests honor the Modelfile context and keep the model warm")

    payload = _payload_for(
        OllamaClient(
            host="http://127.0.0.1:11434",
            model="raza-edge:4b-v3",
            num_ctx=4096,
            keep_alive="15m",
        )
    )
    assert payload["options"]["num_ctx"] == 4096
    assert payload["keep_alive"] == "15m"
    print("[PASS] explicit context/keep-alive overrides remain available")

    config = Path("app/config.py").read_text(encoding="utf-8")
    assert "RAZAAI_OLLAMA_NUM_CTX" in config
    assert "RAZAAI_OLLAMA_KEEP_ALIVE" in config
    print("[PASS] edge runtime tuning is configurable without source edits")

    print()
    print("=" * 72)
    print("STEP 20.3 CAPABILITY TRUTH + EDGE RUNTIME PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
