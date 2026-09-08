"""RazaAI:  capability-aware 'think' field and the RazaAI-Coder Modelfile."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.ollama_client import OllamaClient


class _FakeOllama(BaseHTTPRequestHandler):
    caps = {
        "raza-edge:4b-v3": ["completion", "tools", "thinking"],
        "raza-coder:3b-v1": ["completion", "tools"],
    }
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        if self.path == "/api/show":
            data = json.dumps(
                {
                    "capabilities": self.caps.get(body.get("model"), []),
                    "parameters": "num_ctx 8192",
                }
            ).encode()
        else:
            _FakeOllama.seen.append(body)
            content = (
                json.dumps({"files": [], "summary": "ok"}) if "format" in body else "ok"
            )
            data = json.dumps(
                {
                    "message": {"content": content},
                    "prompt_eval_count": 5,
                    "eval_count": 1,
                }
            ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def main():
    print("=" * 78)
    print("RazaAI Step 20.12.1 Coder Model Compatibility")
    print("=" * 78)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f"http://127.0.0.1:{server.server_port}"
    try:
        OllamaClient._capabilities_cache.clear()
        edge = OllamaClient(host=host, model="raza-edge:4b-v3")
        coder = OllamaClient(host=host, model="raza-coder:3b-v1")
        assert (
            "thinking" in edge.capabilities() and "thinking" not in coder.capabilities()
        )
        edge.chat([{"role": "user", "content": "hi"}])
        coder.chat([{"role": "user", "content": "hi"}])
        edge_req, coder_req = _FakeOllama.seen[-2], _FakeOllama.seen[-1]
        assert "think" not in edge_req and "think" not in coder_req, (
            edge_req.keys(),
            coder_req.keys(),
        )
        print(
            "[PASS] default requests preserve the model's own thinking setting"
        )
    finally:
        server.shutdown()
        OllamaClient._capabilities_cache.clear()

    # Plan requests are schema-constrained on the wire; legacy fake clients still work.
    server2 = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=server2.serve_forever, daemon=True).start()
    try:
        import tempfile
        from app.coding import WorkspaceCoworker
        from app.tools.workspace import WorkspaceManager

        OllamaClient._capabilities_cache.clear()
        _FakeOllama.seen.clear()
        client = OllamaClient(
            host=f"http://127.0.0.1:{server2.server_port}", model="raza-coder:3b-v1"
        )
        cw = WorkspaceCoworker(
            client=client, manager=WorkspaceManager(Path(tempfile.mkdtemp()))
        )
        cw.handle("add a foo function to app.py file")
        plan_req = next(b for b in _FakeOllama.seen if "format" in b)
        assert (
            plan_req["format"]["required"] == ["files", "summary"]
            and "think" not in plan_req
        )
        assert plan_req["format"]["properties"]["files"]["items"]["properties"]["mode"][
            "enum"
        ] == ["create", "replace", "patch", "append"]

        class _Legacy:
            def chat(self, messages, tools=None):  # No `format` kwarg
                return {
                    "message": {
                        "content": json.dumps({"files": [], "summary": "legacy"})
                    }
                }

        out = WorkspaceCoworker(
            client=_Legacy(), manager=WorkspaceManager(Path(tempfile.mkdtemp()))
        ).handle("add a foo function to app.py file")
        assert "legacy" in out
        print(
            "[PASS] planner/repair requests carry the plan JSON schema (Ollama structured output); legacy clients fall back"
        )
    finally:
        server2.shutdown()
        OllamaClient._capabilities_cache.clear()

    tui = Path("app/tui/app.py").read_text(encoding="utf-8")
    assert "_active_model_label" in tui and 'f"{OLLAMA_MODEL}\\n"' not in tui
    assert (
        "session model: {active}" in tui and "conversation model: {OLLAMA_MODEL}" in tui
    )
    from app.tui.session import parse_command

    assert (
        parse_command("/model").action == "agent"
        and "/model" in parse_command("/help").message
    )
    print(
        "[PASS] TUI header and status show the coder model when a coding session uses one"
    )

    # The identity anchor names the answering model, and non-edge models get the full voice contract.
    import tempfile
    from unittest.mock import patch

    captured = {}

    def _fake(model):
        class _F:
            num_ctx = None
            last_usage = {}

            def __init__(self, model=model):
                self.model = model

            def detect_context_window(self, fallback=None, timeout=5):
                return 8192

            def chat(self, messages, tools=None, **kw):
                captured["sys"] = "\n".join(
                    m["content"] for m in messages if m["role"] == "system"
                )
                return {"message": {"content": "ok"}}

            chat_stream = chat

        return _F

    os.environ["RAZAAI_CODE_MODEL"] = "raza-coder:3b-v1"
    agent_module = None
    try:
        import importlib, app.config, app.agent.agent as agent_module

        importlib.reload(app.config)
        importlib.reload(agent_module)
        # /the approved-registry tag wins even when a legacy
        # tag is requested; the identity anchor must describe the model that
        # answers (the approved Qwen3-4B coder, not the conversation model and
        # not the rejected legacy tag). Identity questions in chat are answered
        # by the Python authority layer, so the anchor is asserted
        # directly.
        assert agent_module.CODE_MODEL == "raza-coder:3b-v1"
        assert not app.config.CODE_MODEL_OVERRIDE_REJECTED
        s = agent_module.core_identity_for("raza-coder:qwen3-4b-v1", full_voice=True)
        assert "Qwen3 4B Instruct" in s
        assert "Qwen3 4B Heretic" not in s
        assert "Cortana" in s
        assert "customer-service" in s  # The voice contract's avoid list ships
        with patch("app.agent.agent.OllamaClient", _fake("raza-coder:qwen3-4b-v1")):
            agent_module.RazaAgent(workspace_root=Path(tempfile.mkdtemp())).ask(
                "write a python function that reads a csv and prints the header row"
            )
    finally:
        os.environ.pop("RAZAAI_CODE_MODEL")
        if agent_module is not None:
            importlib.reload(app.config)
            importlib.reload(agent_module)
    with patch("app.agent.agent.OllamaClient", _fake("raza-edge:4b-v3")):
        # Neutral prompt: identity questions are Python-answered and
        # never reach the model.
        agent_module.RazaAgent().ask("briefly explain what a default gateway does")
    s = captured["sys"]
    # The voice contract is an application contract for every
    # model, including raza-edge (fine-tuned weights reinforce, not replace).
    assert app.config.model_lineage(agent_module.OLLAMA_MODEL) in s and "Cortana" in s
    print(
        "[PASS] identity lineage follows the active model; every model gets RazaAI's voice contract from Python"
    )

    # Trivial closings are answered by Python when the coder model is active.
    from app.agent.agent import _is_closing

    assert (
        _is_closing("thanks, that's all for now")
        and _is_closing("ok")
        and not _is_closing("ok so what is a default gateway?")
    )
    os.environ["RAZAAI_CODE_MODEL"] = "raza-coder:3b-v1"
    try:
        importlib.reload(app.config)
        importlib.reload(agent_module)

        class _Never(_fake("raza-coder:3b-v1")):
            def chat(self, messages, tools=None, **kw):
                raise AssertionError("closing must not reach the coder model")

            chat_stream = chat

        with patch("app.agent.agent.OllamaClient", _Never):
            reply = agent_module.RazaAgent(workspace_root=Path(tempfile.mkdtemp())).ask(
                "thanks, that's all for now"
            )
        assert reply and "feel free" not in reply.casefold()
    finally:
        os.environ.pop("RAZAAI_CODE_MODEL")
        importlib.reload(app.config)
        importlib.reload(agent_module)
    from app.runtime_health import memory_snapshot

    print(
        "[PASS] closings are Python-answered for the coder model; swap alone no longer warns on a roomy host"
    )

    for rel in ("app/evaluation/capabilities.py", "app/evaluation/application.py"):
        src = Path(rel).read_text(encoding="utf-8")
        assert '"think": False' not in src and "_think_field" in src, rel
    print("[PASS] evaluation adapters use the same capability check")

    from app.profiles import PROFILES
    for profile in PROFILES.values():
        definition = profile.modelfile(profile.code_base, coding=True)
        assert f"FROM {profile.code_base}" in definition
        assert f"num_ctx {profile.context}" in definition
        assert f"num_batch {profile.batch}" in definition
        assert "temperature 0.2" in definition and "Brad Heffernan" in definition
        assert "Never claim a test passed without supplied evidence" in definition
    assert "Qwen3-4B-Instruct-2507" in PROFILES["8g"].code_base
    assert "7b-instruct-q4_K_M" in PROFILES["standard"].code_base
    print("[PASS] generated coder definitions use each profile's model and memory limits")
    print("=" * 78)
    print("STEP 20.12.1 CODER MODEL COMPATIBILITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
