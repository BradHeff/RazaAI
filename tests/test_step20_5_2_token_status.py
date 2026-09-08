"""RazaAI token status regression."""

import json
from unittest.mock import patch
from pathlib import Path

from app.ollama_client import OllamaClient


class _Response:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self):
        return json.dumps({
            "message": {"role": "assistant", "content": "Hello."},
            "done": True,
            "prompt_eval_count": 2345,
            "eval_count": 167,
        }).encode("utf-8")


def main():
    print("=" * 76)
    print("RazaAI Step 20.5.2 Token Status")
    print("=" * 76)

    client = OllamaClient(
        host="http://127.0.0.1:11434",
        model="raza-edge:4b-v3",
        num_ctx=4096,
    )
    with patch("app.ollama_client.urllib.request.urlopen", lambda *a, **k: _Response()):
        client.chat([{"role": "user", "content": "hi"}])

    assert client.last_usage["prompt_tokens"] == 2345
    assert client.last_usage["output_tokens"] == 167
    assert client.last_usage["context_window"] == 4096
    print("[PASS] Ollama prompt/output counters are retained authoritatively")

    tui = Path("app/tui/app.py").read_text(encoding="utf-8")
    assert 'with Horizontal(id="status")' in tui
    assert 'id="status-left"' in tui
    assert 'id="status-tokens"' in tui
    assert "In {self._format_tokens" in tui
    assert "Out {self._format_tokens" in tui
    assert "Ctx {self._context_window()}" in tui  # Live window from Ollama
    assert "_capture_last_usage()" in tui
    print("[PASS] token usage is anchored on the right side of the fixed status bar")

    session = Path("app/tui/session.py").read_text(encoding="utf-8")
    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert 'CommandResult(True, "improve", topic=topic)' in session
    assert "def run_self_improvement" in agent
    assert "_format_improvement_summary" in agent
    print("[PASS] /improve remains the controlled IMPROVE-job workflow")

    print()
    print("=" * 76)
    print("STEP 20.5.2 TOKEN STATUS PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
