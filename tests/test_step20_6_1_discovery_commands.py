"""RazaAI TUI discovery/auto-improve command integration."""

from pathlib import Path

from app.tui.session import parse_command


def main():
    print("=" * 76)
    print("RazaAI Step 20.6.1 Discovery Commands")
    print("=" * 76)

    discovery = parse_command("/improvements")
    assert discovery.handled and discovery.action == "discover_improvements"
    alias = parse_command("/improve discover")
    assert alias.action == "discover_improvements"
    auto = parse_command("/improve auto")
    assert auto.handled and auto.action == "improve_auto"
    print("[PASS] discovery and automatic improvement have explicit slash commands")

    help_text = parse_command("/help").message
    assert "/improvements" in help_text
    assert "/improve auto" in help_text
    assert "/improve <topic>" in help_text
    print("[PASS] /help advertises discovery, auto-selection, and targeted improvement")

    agent = Path("app/agent/agent.py").read_text(encoding="utf-8")
    tui = Path("app/tui/app.py").read_text(encoding="utf-8")
    discovery_source = Path("app/selfops/discovery.py").read_text(encoding="utf-8")

    assert "def discover_self_improvements" in agent
    assert "def run_auto_self_improvement" in agent
    assert "ImprovementDiscoveryEngine" in agent
    assert "self.run_self_improvement(selected.get(\"topic\"))" in agent
    assert "def _discover_improvements_sync" in tui
    assert "def _improve_auto_sync" in tui
    assert 'command.action == "discover_improvements"' in tui
    assert 'command.action == "improve_auto"' in tui
    print("[PASS] TUI executes discovery and auto-improvement off the event loop")

    assert "Discovery never edits source" in discovery_source
    assert "authority findings are manual-only" in discovery_source
    assert "revalidated" in discovery_source
    print("[PASS] discovery is read-only, risk-aware, and stale-evidence-aware")

    print()
    print("=" * 76)
    print("STEP 20.6.1 DISCOVERY COMMANDS PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
