"""RazaAI technical reasoning, memory authority, and slash commands."""

import ast
import re
from pathlib import Path

from app.tui.session import parse_command
from app.playbooks.technical_guidance import networking_reasoning_guidance


def _load_helpers():
    source = Path("app/agent/agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"_historical_resolution_override_guidance"}
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {"re": re}
    exec(compile(module, "<step20.5-helpers>", "exec"), namespace)
    return namespace


class Learned:
    root_cause = "Staff at the example campus used Access VLAN 30 instead of VLAN 80"
    resolution = "Changed Staff WLAN Access VLAN to VLAN 80"
    playbook_id = "wifi-nps-no-connectivity"


def main():
    print("=" * 76)
    print("RazaAI Step 20.5 Technical Reasoning + Memory Authority + Commands")
    print("=" * 76)

    helpers = _load_helpers()
    networking = networking_reasoning_guidance
    override = helpers["_historical_resolution_override_guidance"]

    voice = networking(
        "what if i want to check 1 way audio on NEC phone for internal calls "
        "between campus over ipsec VPN tunnel?"
    )
    for phrase in ("SIP signalling", "RTP", "Phase 2 selectors", "NAT", "packet capture"):
        assert phrase in voice
    assert "both" in voice.casefold()
    print("[PASS] NEC/IPsec guidance separates SIP signalling from bidirectional RTP evidence")

    nps = networking("how to fix nps issue with eap wifi?")
    for phrase in ("Event Viewer", "reason code", "Network Policy", "PEAP/MS-CHAPv2", "certificate", "Access-Accept"):
        assert phrase in nps
    assert "Do not jump straight to a remembered VLAN fix" in nps
    print("[PASS] NPS/EAP guidance diagnoses the authentication layer before historical fixes")

    current = override("its on vlan 80", [Learned()])
    assert "CURRENT EVIDENCE OVERRIDES HISTORICAL RESOLUTION" in current
    assert "falsifies" in current
    assert "do not recommend changing to VLAN 80 again" in current
    assert "NPS event/reason code" in current
    print("[PASS] current VLAN evidence retires the contradicted historical VLAN hypothesis")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    assert "previous_learned_resolutions" in agent
    assert "historical_override_guidance" in agent
    assert "networking_reasoning_guidance" in agent
    print("[PASS] current-evidence and technical-reasoning guidance are wired into agent turns")

    audit = parse_command("/audit")
    assert audit.handled and audit.action == "agent"
    assert "audit your code" in audit.prompt
    full = parse_command("/audit full")
    assert full.action == "agent" and "full audit" in full.prompt
    improve = parse_command("/improve FortiGate IPsec troubleshooting")
    assert improve.action == "improve"
    assert improve.topic == "FortiGate IPsec troubleshooting"
    assert improve.prompt is None
    usage = parse_command("/improve")
    assert usage.action == "message" and "Usage" in usage.message
    print("[PASS] /audit and /improve slash commands map into controlled workflows")

    help_result = parse_command("/help")
    assert "/audit" in help_result.message
    assert "/audit full" in help_result.message
    assert "/improve <topic>" in help_result.message
    print("[PASS] /help advertises the self-audit and controlled self-improvement commands")

    tui = Path("app/tui/app.py").read_text(encoding="utf-8")
    assert "agent_prompt = prompt" in tui
    assert "command.action == \"agent\"" in tui
    assert "self._ask_sync, agent_prompt" in tui
    print("[PASS] slash agent commands use the normal non-blocking TUI execution path")

    memory = Path("app/memory/manager.py").read_text(encoding="utf-8")
    learned = Path("app/incidents/resolutions.py").read_text(encoding="utf-8")
    prior = Path("app/incidents/retrieval.py").read_text(encoding="utf-8")
    assert "explicit current user state outrank memory" in memory
    assert "historical hypothesis falsified" in learned
    assert "current user/tool evidence contradicts" in prior
    print("[PASS] persistent and validated historical memory explicitly yield to current evidence")

    print()
    print("=" * 76)
    print("STEP 20.5 TECHNICAL REASONING + MEMORY AUTHORITY + COMMANDS PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
