"""RazaAI:  service mode: health without Ollama, bearer auth, NDJSON stream contract, serialised turns, session pool, stdlib client, deploy assets."""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from app.server import RazaService, SessionPool, make_handler


class _FakeAgent:
    """Streams two deltas then returns the final content; records call order."""
    calls = []
    active = 0
    max_active = 0

    def __init__(self):
        self.context_window = 8192
        self.client = type("C", (), {"last_usage": {"prompt_tokens": 123, "output_tokens": 45}})()

    def ask(self, message, on_stream=None):
        _FakeAgent.active += 1
        _FakeAgent.max_active = max(_FakeAgent.max_active, _FakeAgent.active)
        _FakeAgent.calls.append(message)
        if on_stream:
            on_stream("Hello, ")
            time.sleep(0.05)
            on_stream("world.")
        _FakeAgent.active -= 1
        return "Hello, world."


def _start(service):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


def _get(url, token=None):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _chat(url, token, message, session="t"):
    req = urllib.request.Request(
        url + "/v1/chat",
        data=json.dumps({"session": session, "message": message}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return [json.loads(line) for line in resp.read().decode("utf-8").splitlines() if line.strip()]


def main():
    print("=" * 78)
    print("RazaAI Step 20.9.0 Service Mode")
    print("=" * 78)

    # Hermetic: pretend Ollama is down regardless of the host running this test.
    import app.server as server_module
    server_module.ollama_status = lambda *a, **k: {
        "reachable": False, "model_present": False, "model_loaded": False, "error": "tags: simulated"}
    service = RazaService(agent_factory=_FakeAgent, token="test-token")
    httpd, url = _start(service)
    try:
        code, health = _get(url + "/healthz")
        assert code == 503 and health["status"] == "degraded"
        assert any("ollama" in d for d in health["degraded"])
        assert health["version"] and "memory" in health and "selfops_enabled" in health
        print("[PASS] /healthz answers without Ollama and reports degraded with the reason (no auth needed)")

        code, body = _get(url + "/v1/sessions")
        assert code == 401 and "token" in body["error"]
        code, body = _get(url + "/v1/sessions", token="wrong")
        assert code == 401
        print("[PASS] every API route requires the bearer token")

        records = _chat(url, "test-token", "hi there")
        deltas = [r["delta"] for r in records if "delta" in r]
        done = [r for r in records if r.get("done")]
        assert deltas == ["Hello, ", "world."], records
        assert len(done) == 1 and done[0]["content"] == "Hello, world." and done[0]["session"] == "t"
        assert done[0]["prompt_tokens"] == 123 and done[0]["context_window"] == 8192
        print("[PASS] /v1/chat streams NDJSON deltas and ends with one done record carrying the final content")

        _FakeAgent.max_active = 0
        threads = [threading.Thread(target=_chat, args=(url, "test-token", f"q{i}", f"s{i}")) for i in range(4)]
        for t in threads: t.start()
        for t in threads: t.join(10)
        assert _FakeAgent.max_active == 1, _FakeAgent.max_active
        print("[PASS] concurrent clients are serialised to one agent turn at a time (one Ollama slot)")

        code, body = _get(url + "/v1/sessions", token="test-token")
        ids = {s["id"] for s in body["sessions"]}
        assert "s3" in ids and len(ids) <= 4 and "t" not in ids  # 5 sessions used, oldest evicted
        req = urllib.request.Request(url + "/v1/sessions/s3", headers={"Authorization": "Bearer test-token"}, method="DELETE")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert json.loads(resp.read())["dropped"] is True
        print("[PASS] sessions are listable, bounded, and droppable")

        pool = SessionPool(_FakeAgent, max_sessions=2, idle_seconds=60)
        for sid in ("a", "b", "c"):
            pool.get(sid)
        assert [s["id"] for s in pool.describe()] == ["b", "c"]
        print("[PASS] session pool evicts least-recently-used beyond its bound")

        code, page = urllib.request.urlopen(url + "/", timeout=5).status, urllib.request.urlopen(url + "/", timeout=5).read().decode()
        assert code == 200 and "/v1/chat" in page and "Authorization" in page
        print("[PASS] bundled web client is served and talks to the same API")

        env = dict(os.environ, RAZAAI_URL=url, RAZAAI_TOKEN="test-token", RAZAAI_SESSION="cli")
        out = subprocess.run([sys.executable, "bin/raza", "ping", "from", "cli"], env=env, capture_output=True, text=True, timeout=20)
        assert out.returncode == 0 and out.stdout.strip() == "Hello, world.", out
        assert "ping from cli" in _FakeAgent.calls
        out = subprocess.run([sys.executable, "bin/raza", "--health"], env=env, capture_output=True, text=True, timeout=20)
        assert out.returncode == 1 and "degraded" in out.stdout
        print("[PASS] bin/raza (stdlib only) streams answers and reports health with a non-zero exit when degraded")
    finally:
        httpd.shutdown()

    # Startup warm-up loads the model via /api/generate with an empty prompt.
    from http.server import BaseHTTPRequestHandler
    seen = {}

    class _FakeOllama(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["body"] = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            data = b'{"done": true}'
            self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def log_message(self, *a): pass

    fake = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    try:
        result = server_module.warm_model(host=f"http://127.0.0.1:{fake.server_port}", model="raza-edge:4b-v3")
        assert result["loaded"] and seen["path"] == "/api/generate"
        assert seen["body"]["model"] == "raza-edge:4b-v3" and seen["body"]["prompt"] == ""
        assert seen["body"]["keep_alive"] == server_module.OLLAMA_KEEP_ALIVE
        from app.ollama_client import OllamaClient, normalize_keep_alive
        assert normalize_keep_alive("-1") == -1 and normalize_keep_alive("0") == 0
        assert normalize_keep_alive("30m") == "30m" and normalize_keep_alive(None) == "30m"
        assert OllamaClient(keep_alive="-1").keep_alive == -1
        bad = subprocess.run([sys.executable, "bin/raza", "--helth"], env=env, capture_output=True, text=True, timeout=20)
        assert bad.returncode == 64 and "unknown option" in bad.stderr and "--helth" not in _FakeAgent.calls
        down = server_module.warm_model(host="http://127.0.0.1:9", model="x", timeout=1)
        assert not down["loaded"] and down["error"]
        svc2 = RazaService(agent_factory=_FakeAgent, token="t2")
        assert "warmup" in svc2.health() and svc2.health()["warmup"]["requested"] is False
        assert "RAZAAI_SERVER_WARMUP" in Path("app/server.py").read_text(encoding="utf-8")
        print("[PASS] service warms the model at startup (empty prompt with configured keep_alive) and reports it in /healthz")
    finally:
        fake.shutdown()

    for rel in ("deploy/razaai-server.service", "deploy/razaai-server.env", "deploy/ollama-override.conf",
                "deploy/jetson-headless.sh", "docs/ROAD_SETUP.md", "app/web/index.html"):
        assert Path(rel).is_file(), rel
    override = Path("deploy/ollama-override.conf").read_text(encoding="utf-8")
    for key in ("OLLAMA_FLASH_ATTENTION=1", "OLLAMA_KV_CACHE_TYPE=q8_0", "OLLAMA_NUM_PARALLEL=1", "LLAMA_ARG_CACHE_RAM=0"):
        assert key in override, key
    assert "MemoryMax" in Path("deploy/razaai-server.service").read_text(encoding="utf-8")
    assert "192.168.55.1" in Path("docs/ROAD_SETUP.md").read_text(encoding="utf-8")
    print("[PASS] deploy assets carry the measured Jetson runtime settings and the road guide")

    print("=" * 78)
    print("STEP 20.9.0 SERVICE MODE PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
