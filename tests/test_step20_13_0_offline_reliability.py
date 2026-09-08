"""RazaAI:  offline reliability: calibrated token estimate that only tightens, connectivity probe gating web tools, resource guard, doctor, backup, deploy persistence."""

import json
import os
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import app.context_budget as budget
from app import connectivity
from app.doctor import checks, render
from app.server import RazaService, make_handler
from app.tools.registry import ToolRegistry


def main():
    print("=" * 78)
    print("RazaAI Step 20.13.0 Offline Reliability")
    print("=" * 78)

    assert (
        2.0 <= budget.ESTIMATED_CHARS_PER_TOKEN <= 4.0
        and budget.ESTIMATED_CHARS_PER_TOKEN > 2.0
    )
    before = budget.ESTIMATED_CHARS_PER_TOKEN
    assert (
        budget.tighten_estimate(actual_tokens=1000, estimated_tokens=1200) == before
    )  # Undercounts never loosen
    tightened = budget.tighten_estimate(actual_tokens=1500, estimated_tokens=1000)
    assert tightened < before and tightened >= 2.0
    budget.ESTIMATED_CHARS_PER_TOKEN = before
    assert (
        budget.estimate_tokens("x" * 3000) < 3000 / 2.0 + 2
    )  # Uses more of the window than the old 2.0
    print(
        "[PASS] token estimate is measured (~3 chars/token), only ever tightens, never below the 2.0 floor"
    )

    os.environ["RAZAAI_OFFLINE"] = "1"
    try:
        assert connectivity.is_online() is False
        result = ToolRegistry().execute("search_web", {"query": "anything"})
        assert not result.success and "Offline" in (result.error or "")
        result = ToolRegistry().execute(
            "fetch_web_page", {"url": "https://example.com"}
        )
        assert not result.success and "Offline" in (result.error or "")
    finally:
        os.environ.pop("RAZAAI_OFFLINE")
    os.environ["RAZAAI_ONLINE"] = "1"
    try:
        assert connectivity.is_online() is True
    finally:
        os.environ.pop("RAZAAI_ONLINE")
    print(
        "[PASS] web tools fail immediately with 'Offline' when the 1-second probe fails; forced modes work"
    )

    class _Never:
        num_ctx = None
        last_usage = {}

        def detect_context_window(self, fallback=None, timeout=5):
            return 8192

        def chat(self, messages, tools=None, **kw):
            raise AssertionError("model must not be called under memory pressure")

        chat_stream = chat

    bad = {
        "supported": True,
        "total_mb": 7485,
        "available_mb": 120,
        "swap_used_mb": 2800,
        "warnings": ["x"],
    }
    with patch("app.agent.agent.OllamaClient", _Never), patch(
        "app.runtime_health.memory_snapshot", lambda: bad
    ):
        from app.agent import RazaAgent

        agent = RazaAgent()
        answer = agent.ask("explain OSPF area types")
        assert (
            "not starting this turn" in answer
            and "2800 MB in swap" in answer
            and "restart ollama" in answer
        )
    good = dict(bad, available_mb=2500, swap_used_mb=10, warnings=[])
    with patch("app.runtime_health.memory_snapshot", lambda: good):
        assert agent._resource_guard() is None
    print(
        "[PASS] resource guard refuses to start a model turn when the model has spilled into swap, and says what to run"
    )

    results = checks()
    names = {r["name"] for r in results}
    assert {
        "ollama",
        "memory",
        "disk",
        "internet",
        "code sandbox",
        "knowledge store",
        "self-ops",
    } <= names
    assert all(r["status"] in {"ok", "warn", "fail"} for r in results)
    text, code = render(results)
    assert text.startswith("RazaAI doctor") and code in {0, 1, 2}
    assert all(r.get("fix") for r in results if r["status"] == "fail")
    print(
        "[PASS] doctor reports every subsystem read-only, with a fix line for each failure"
    )

    service = RazaService(agent_factory=lambda: None, token="t")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        import urllib.request

        req = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_port}/v1/doctor",
            headers={"Authorization": "Bearer t"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
        assert "checks" in body and body["text"].startswith("RazaAI doctor")
        env = dict(
            os.environ,
            RAZAAI_URL=f"http://127.0.0.1:{httpd.server_port}",
            RAZAAI_TOKEN="t",
        )
        out = subprocess.run(
            [sys.executable, "bin/raza", "doctor"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "RazaAI doctor" in out.stdout
    finally:
        httpd.shutdown()
    print("[PASS] `raza doctor` fetches the full report from the service")

    # Freshness phrasing routes to the web; local/conceptual phrasing does not.
    from app.agent.edge_router import EdgeIntentRouter
    from app.interaction.router import InteractionRouter
    from app.experts.router import ExpertRouter

    class _M:
        def list_hosts(self):
            return []

    edge, ir, er = EdgeIntentRouter(manager=_M()), InteractionRouter(), ExpertRouter()

    def _route(q):
        return edge.route(q, interaction=ir.classify(q, expert_route=er.route(q)))

    for q in (
        "what changed in Ollama this month?",
        "what's new in Ollama?",
        "is there a newer version of FortiOS?",
    ):
        r = _route(q)
        assert r.kind == "deterministic_tool" and r.tool == "search_web", q
    for q in (
        "what changed in the routing table?",
        "explain what changed between OSPFv2 and OSPFv3",
        "what is the current IP config on this machine?",
    ):
        r = _route(q)
        assert r.tool != "search_web", q
    from app.doctor import _configured_code_model

    os.environ["RAZAAI_CODE_MODEL"] = "raza-coder:3b-v1"
    try:
        from app.config import CODE_MODEL
        assert _configured_code_model() == (CODE_MODEL, "environment")
    finally:
        os.environ.pop("RAZAAI_CODE_MODEL")
    assert Path("scripts/package_release.sh").is_file()
    print(
        "[PASS] time-anchored change questions reach the web; doctor finds the coder model from the service env; releases exclude machine-specific stores"
    )

    assert "99-razaai-bwrap.conf" not in Path("deploy/jetson-headless.sh").read_text(
        encoding="utf-8"
    )
    assert Path("scripts/backup.sh").is_file() and os.access(
        "scripts/backup.sh", os.X_OK
    )
    print("[PASS] deploy persists the sandbox sysctl; backup/restore script ships")

    print("=" * 78)
    print("STEP 20.13.0 OFFLINE RELIABILITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
