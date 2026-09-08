"""RazaAI:  the Ollama Modelfile, not a hard-coded constant, sets the context window."""

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.ollama_client import OllamaClient
from app.tools.workspace import WorkspaceManager


class _FakeOllama(BaseHTTPRequestHandler):
    num_ctx = 8192

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        if self.path == "/api/show":
            body = {
                "parameters": f"num_ctx {self.num_ctx}\ntemperature 0.6\nstop \"<|im_end|>\"",
                "details": {"family": "qwen3"},
            }
            data = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.3 Context Window Authority")
    print("=" * 78)

    server = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"http://127.0.0.1:{server.server_port}"

    try:
        client = OllamaClient(host=host, model="raza-edge:4b-v3", num_ctx=None)
        assert client.detect_context_window(fallback=4096) == 8192
        assert client.last_usage["context_window"] == 8192
        print("[PASS] num_ctx from the Ollama Modelfile is detected via /api/show")

        explicit = OllamaClient(host=host, model="raza-edge:4b-v3", num_ctx=6144)
        assert explicit.detect_context_window(fallback=4096) == 6144
        print("[PASS] an explicit num_ctx override wins over the Modelfile")
    finally:
        server.shutdown()

    down = OllamaClient(host="http://127.0.0.1:9", model="raza-edge:4b-v3", num_ctx=None)
    assert down.detect_context_window(fallback=4096, timeout=1) == 4096
    print("[PASS] unreachable Ollama falls back safely without raising")

    modelfile = Path("Modelfile.raza-edge-v3").read_text(encoding="utf-8")
    assert "PARAMETER num_ctx" in modelfile
    config = Path("app/config.py").read_text(encoding="utf-8")
    assert "OLLAMA_CONTEXT_WINDOW_OVERRIDE" in config
    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "detect_context_window(" in agent
    assert "context_window=OLLAMA_CONTEXT_WINDOW" not in agent
    print("[PASS] agent budgets follow the detected window, not the old constant")

    ws = Path(tempfile.mkdtemp())
    small = WorkspaceCoworker(client=None, manager=WorkspaceManager(ws), context_window=4096)
    large = WorkspaceCoworker(client=None, manager=WorkspaceManager(ws), context_window=8192)
    assert small.planner_chars == WorkspaceCoworker.BASE_PLANNER_CHARS
    assert large.planner_chars == 2 * small.planner_chars
    assert large.REPAIR_READ_CHARS == 2 * small.REPAIR_READ_CHARS
    huge = WorkspaceCoworker(client=None, manager=WorkspaceManager(ws), context_window=65536)
    assert huge.planner_chars == 4 * small.planner_chars
    print("[PASS] coworker source budgets scale with the window and are capped")

    print("=" * 78)
    print("STEP 20.8.3 CONTEXT WINDOW AUTHORITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
