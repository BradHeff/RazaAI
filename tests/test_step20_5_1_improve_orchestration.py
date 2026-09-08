"""RazaAI improve orchestration + NPS entry authority."""

from pathlib import Path

from app.agent.edge_router import EdgeIntentRouter
from app.tui.session import parse_command


def main():
    print("=" * 76)
    print("RazaAI Step 20.5.1 Improve Orchestration")
    print("=" * 76)

    command = parse_command("/improve NPS EAP WiFi troubleshooting")
    assert command.handled
    assert command.action == "improve"
    assert command.topic == "NPS EAP WiFi troubleshooting"
    assert command.prompt is None
    print("[PASS] /improve is a first-class TUI action, not prompt shorthand")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    orchestrator = Path("app/selfops/orchestrator.py").read_text(encoding="utf-8")
    assert "def run_self_improvement" in agent
    assert "ControlledImprovementOrchestrator" in agent
    assert '"investigate_project_code"' in orchestrator
    assert '"start_self_improvement"' in orchestrator
    assert '"stage_improvement_patch"' in orchestrator
    assert '"verify_self_improvement"' in orchestrator
    assert "_format_improvement_summary" in agent
    assert "Approve {improvement_id}" in agent
    print("[PASS] Python owns inspect -> plan -> stage -> verify orchestration")

    tui = Path("app/tui/app.py").read_text(encoding="utf-8")
    assert "def _improve_sync" in tui
    assert 'command.action == "improve"' in tui
    assert "run_self_improvement" in tui
    assert "asyncio.to_thread(self._improve_sync" in tui
    print("[PASS] improvement orchestration runs off the Textual event loop")

    router = EdgeIntentRouter(manager=object())
    route = router.route("how to fix nps issue with eap wifi?")
    assert route.kind == "deterministic_response"
    response = route.response.lower()
    assert "nps/radius evidence" in response
    assert "event/reason code" in response
    assert "network policy" in response
    assert "eap method" in response
    assert "access-accept" in response
    assert "historical evidence" in response
    print("[PASS] first NPS/EAP answer starts with current RADIUS evidence, not VLAN history")

    print()
    print("=" * 76)
    print("STEP 20.5.1 IMPROVE ORCHESTRATION PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
