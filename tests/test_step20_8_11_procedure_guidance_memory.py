"""RazaAI:  procedure requests get the full ordered method with the whole reference document; FortiGate answers must name evidence; startup memory check; capability eval supports stability runs."""

from pathlib import Path
from unittest.mock import patch

from app.diagnostics.engine import DiagnosticEngine, is_procedure_request
from app.experts.router import ExpertRouter
from app.runtime_health import format_memory_line, memory_snapshot

IPSEC = ("A FortiGate IPsec tunnel is down. Give me a systematic troubleshooting "
         "order without changing configuration.")
NGINX = "Nginx returns 502 Bad Gateway for a local application. What should I verify first?"


class _Capture:
    num_ctx = None
    last_usage = {}

    def __init__(self):
        self.system = ""

    def detect_context_window(self, fallback=None, timeout=5):
        return 8192

    def chat(self, messages, tools=None):
        self.system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        return {"message": {"content": "ok"}}

    def chat_stream(self, messages, tools=None, on_chunk=None):
        return self.chat(messages, tools)


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.9 Procedure Guidance + Memory Visibility")
    print("=" * 78)

    assert is_procedure_request(IPSEC)
    assert is_procedure_request("walk me through troubleshooting NPS step by step")
    assert not is_procedure_request(NGINX)
    assert not is_procedure_request("the tunnel to site B is down")
    print("[PASS] 'systematic order / step by step' is a procedure request; 'verify first' is not")

    engine = DiagnosticEngine()
    router = ExpertRouter()
    ctx = engine.build_context(IPSEC, router.route(IPSEC))
    assert ctx.is_troubleshooting and ctx.procedure_request
    guidance = engine.guidance(ctx)
    assert "PROCEDURE RULES" in guidance
    assert "Preferred answer structure" not in guidance
    for section in ("## 2. Phase 1 (IKE SA)", "## 3. Phase 2 (IPsec SA / selectors)",
                    "## 4. Routing and policy", "diagnose vpn tunnel list"):
        assert section in guidance, section
    assert "Evidence to collect" in guidance
    print("[PASS] procedure guidance carries the whole reference document in order, not just its intro")

    ctx2 = engine.build_context(NGINX, router.route(NGINX))
    assert ctx2.is_troubleshooting and not ctx2.procedure_request
    assert "Primary hypothesis:" in engine.guidance(ctx2)
    print("[PASS] single-question troubleshooting keeps the compact incident template")

    client = _Capture()
    with patch("app.agent.agent.OllamaClient", lambda: client):
        from app.agent import RazaAgent
        agent = RazaAgent()
        agent.ask(IPSEC)
    assert "PROCEDURE RULES" in client.system
    assert "## 3. Phase 2 (IPsec SA / selectors)" in client.system
    assert "matched policy ID" in client.system
    assert len(client.system) // 2 < 8192 - 900
    print("[PASS] agent prompt for the IPsec eval case contains every phase and fits the 8192 budget")


    # The playbook guidance layer and agent.py only wires it into the turn.
    agent_source = Path("app/agent/agent.py").read_text(encoding="utf-8")
    guidance_source = Path("app/playbooks/technical_guidance.py").read_text(encoding="utf-8")
    assert "'Evidence:' line" in guidance_source and "a hypothesis without evidence is incomplete" in guidance_source
    assert "fortigate_turn_guidance" in agent_source
    print("[PASS] FortiGate policy guidance requires a closing Evidence line and remains wired into the agent")

    snap = memory_snapshot()
    line = format_memory_line(snap)
    assert line.startswith("Memory:")
    fake_bad = dict(snap, supported=True, total_mb=7485, available_mb=242, swap_used_mb=2840,
                    warnings=["only 242 MB available; x", "2840 MB in swap; y"])
    assert "WARNING" in format_memory_line(fake_bad)
    assert "WARNING" not in format_memory_line(dict(fake_bad, warnings=[]))
    assert "format_memory_line()" in Path("app/main.py").read_text(encoding="utf-8")
    assert "self.memory_snapshot = memory_snapshot()" in agent_source
    print("[PASS] startup memory line and low-memory/swap warning are wired")

    eval_source = Path("scripts/step15_capability_eval.py").read_text(encoding="utf-8")
    assert '"--runs"' in eval_source and "UNSTABLE" in eval_source
    print("[PASS] capability eval supports --runs stability gating")

    print("=" * 78)
    print("STEP 20.8.9 PROCEDURE GUIDANCE + MEMORY VISIBILITY PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
